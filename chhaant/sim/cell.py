"""A simulated inspection cell in MuJoCo: SO-101 arm, crate, turntable, bins.

The arm is simulated by MuJoCo physics: each joint follows its position
actuator, and targets come from a damped-least-squares inverse kinematics on
the gripper frame that also keeps the gripper pointing down. Produce items are
moved kinematically (mocap bodies that follow the gripper while held); there
is no grasp physics. The cell exists to show the agent's decisions as motion.
The pixels those decisions use are real photographs, replayed by
``chhaant.robot.turntable.VirtualTurntable``.

Needs the SO-101 model: ``python scripts/fetch_so101.py``. Rendering needs an
OpenGL context (MUJOCO_GL=glfw under WSL, egl or osmesa on a headless server).
"""

import os

import mujoco
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SO101_XML = os.path.join(ROOT, "assets", "so101", "so101.xml")

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
ITEM_RADIUS = 0.022
CRATE = np.array([0.20, -0.14, 0.0])
TURNTABLE = np.array([0.24, 0.08, 0.0])
TURNTABLE_TOP = 0.03
BINS = {"pack": np.array([0.04, 0.24, 0.0]), "reject": np.array([0.02, -0.26, 0.0])}
HOVER = 0.09        # height above a spot when approaching it
PHYSICS_PER_FRAME = 8


def _add_box(body, size, rgba, pos=(0, 0, 0)):
    body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=list(size), rgba=list(rgba), pos=list(pos))


def build_spec(item_rgba: list[tuple[float, float, float, float]]) -> mujoco.MjSpec:
    spec = mujoco.MjSpec.from_file(SO101_XML)
    world = spec.worldbody
    world.add_light(pos=[0, 0, 1.5], dir=[0, 0, -1], diffuse=[0.8, 0.8, 0.8])
    world.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[1, 1, 0.01], rgba=[0.86, 0.85, 0.82, 1], pos=[0, 0, -0.001])
    world.add_camera(name="overview", pos=[0.62, 0.0, 0.48], xyaxes=[0, 1, 0, -0.62, 0, 0.78])

    crate = world.add_body(name="crate", pos=CRATE.tolist())
    wall = (0.55, 0.38, 0.22, 1)
    _add_box(crate, (0.085, 0.06, 0.004), wall)
    for sx, sy, px, py in ((0.085, 0.004, 0, 0.06), (0.085, 0.004, 0, -0.06), (0.004, 0.06, 0.085, 0), (0.004, 0.06, -0.085, 0)):
        _add_box(crate, (sx, sy, 0.02), wall, (px, py, 0.02))

    table = world.add_body(name="turntable", pos=TURNTABLE.tolist())
    _add_box(table, (0.03, 0.03, TURNTABLE_TOP / 2), (0.3, 0.3, 0.32, 1), (0, 0, TURNTABLE_TOP / 2))
    plate = table.add_body(name="turntable_plate", pos=[0, 0, TURNTABLE_TOP])
    plate.add_joint(name="turntable", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, 1])
    # The plate rests flush on its base; as colliding geoms the contact friction locked it in place.
    plate.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.055, 0.004, 0], rgba=[0.18, 0.18, 0.2, 1],
                   contype=0, conaffinity=0)
    plate.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.05, 0.004, 0.0045], rgba=[0.95, 0.75, 0.1, 1],
                   pos=[0, 0, 0.001], contype=0, conaffinity=0)
    spec.add_actuator(name="turntable", target="turntable", trntype=mujoco.mjtTrn.mjTRN_JOINT,
                      gaintype=mujoco.mjtGain.mjGAIN_FIXED, biastype=mujoco.mjtBias.mjBIAS_AFFINE,
                      gainprm=[20] + [0] * 9, biasprm=[0, -20, -1] + [0] * 7)

    for name, rgba in (("pack", (0.2, 0.6, 0.3, 1)), ("reject", (0.75, 0.2, 0.2, 1))):
        b = world.add_body(name=f"bin_{name}", pos=BINS[name].tolist())
        _add_box(b, (0.05, 0.05, 0.003), rgba)

    for i, rgba in enumerate(item_rgba):
        item = world.add_body(name=f"item{i}", mocap=True, pos=crate_slot(i, len(item_rgba)).tolist())
        item.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[ITEM_RADIUS, 0, 0], rgba=list(rgba),
                      contype=0, conaffinity=0)
    return spec


def crate_slot(i: int, n: int) -> np.ndarray:
    cols = 3
    r, c = divmod(i, cols)
    rows = (n + cols - 1) // cols
    return CRATE + np.array([(c - (cols - 1) / 2) * 0.052, (r - (rows - 1) / 2) * 0.05, ITEM_RADIUS + 0.004])


class SimCell:
    def __init__(self, item_rgba: list[tuple[float, float, float, float]], width: int = 640, height: int = 480):
        self.model = build_spec(item_rgba).compile()
        self.data = mujoco.MjData(self.model)
        self.n_items = len(item_rgba)
        self.site = self.model.site("gripperframe").id
        self.arm_qpos = [self.model.joint(j).qposadr[0] for j in ARM_JOINTS]
        self.arm_dof = [self.model.joint(j).dofadr[0] for j in ARM_JOINTS]
        self.arm_ctrl = [self.model.actuator(j).id for j in ARM_JOINTS]
        self.gripper_ctrl = self.model.actuator("gripper").id
        self.table_ctrl = self.model.actuator("turntable").id
        self.mocap = [self.model.body(f"item{i}").mocapid[0] for i in range(self.n_items)]
        self.held: int | None = None
        self.on_table: int | None = None
        self.table_angle = 0.0
        self.where = ["crate"] * self.n_items
        self._ik_data = mujoco.MjData(self.model)
        self.width, self.height = width, height
        self._renderer = None
        self.frames: list[np.ndarray] = []
        self.record = False
        mujoco.mj_forward(self.model, self.data)

    # ---- kinematics -------------------------------------------------------
    def tool_pos(self) -> np.ndarray:
        return self.data.site_xpos[self.site].copy()

    def ik(self, target: np.ndarray, iters: int = 300, damping: float = 0.03) -> np.ndarray:
        """Arm joint angles that put the gripper frame at ``target``, pointing down."""
        d = self._ik_data
        d.qpos[:] = self.data.qpos
        lo = self.model.jnt_range[[self.model.joint(j).id for j in ARM_JOINTS], 0]
        hi = self.model.jnt_range[[self.model.joint(j).id for j in ARM_JOINTS], 1]
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        for _ in range(iters):
            mujoco.mj_kinematics(self.model, d)
            mujoco.mj_comPos(self.model, d)
            err_p = target - d.site_xpos[self.site]
            approach = d.site_xmat[self.site].reshape(3, 3)[:, 0]  # gripper frame x axis points out of the jaws
            err_r = 0.3 * np.cross(approach, np.array([0.0, 0.0, -1.0]))
            if np.linalg.norm(err_p) < 1e-4 and np.linalg.norm(err_r) < 1e-3:
                break
            mujoco.mj_jacSite(self.model, d, jacp, jacr, self.site)
            J = np.vstack([jacp[:, self.arm_dof], jacr[:, self.arm_dof]])
            e = np.concatenate([err_p, err_r])
            dq = J.T @ np.linalg.solve(J @ J.T + damping**2 * np.eye(6), e)
            q = d.qpos[self.arm_qpos] + np.clip(dq, -0.2, 0.2)
            d.qpos[self.arm_qpos] = np.clip(q, lo, hi)
        mujoco.mj_kinematics(self.model, d)
        return d.qpos[self.arm_qpos].copy()

    # ---- stepping and rendering ------------------------------------------
    def _sync_items(self) -> None:
        if self.held is not None:
            self.data.mocap_pos[self.mocap[self.held]] = self.tool_pos() - np.array([0, 0, ITEM_RADIUS * 0.6])
        if self.on_table is not None:
            plate = self.data.body("turntable_plate").xpos
            self.data.mocap_pos[self.mocap[self.on_table]] = plate + np.array([0, 0, ITEM_RADIUS + 0.004])
            angle = self.data.qpos[self.model.joint("turntable").qposadr[0]]
            self.data.mocap_quat[self.mocap[self.on_table]] = [np.cos(angle / 2), 0, 0, np.sin(angle / 2)]

    def _frame(self) -> None:
        if not self.record:
            return
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, self.height, self.width)
        self._renderer.update_scene(self.data, camera="overview")
        self.frames.append(self._renderer.render().copy())

    def run(self, seconds: float) -> None:
        steps = int(seconds / self.model.opt.timestep)
        for k in range(steps):
            mujoco.mj_step(self.model, self.data)
            self._sync_items()
            if k % PHYSICS_PER_FRAME == 0:
                self._frame()

    def move_tool(self, target: np.ndarray, seconds: float = 1.2) -> float:
        """Drive the arm so the gripper reaches ``target``; returns the final position error (m)."""
        goal = self.ik(target)
        start = self.data.ctrl[self.arm_ctrl].copy()
        n = 12
        for k in range(1, n + 1):
            self.data.ctrl[self.arm_ctrl] = start + (goal - start) * k / n
            self.run(seconds / n)
        self.run(0.4)
        return float(np.linalg.norm(self.tool_pos() - target))

    def set_gripper(self, open_: bool) -> None:
        self.data.ctrl[self.gripper_ctrl] = 1.2 if open_ else 0.0
        self.run(0.25)

    # ---- the cell's actions ----------------------------------------------
    def item_pos(self, i: int) -> np.ndarray:
        return self.data.mocap_pos[self.mocap[i]].copy()

    def pick(self, i: int) -> None:
        if self.held is not None:
            raise RuntimeError("already holding an item")
        above = self.item_pos(i) + np.array([0, 0, HOVER])
        self.set_gripper(True)
        self.move_tool(above)
        self.move_tool(self.item_pos(i) + np.array([0, 0, ITEM_RADIUS * 0.6]), 0.8)
        if self.on_table == i:
            self.on_table = None
        self.held = i
        self.set_gripper(False)
        self.move_tool(above, 0.8)

    def place(self, where: str) -> None:
        if self.held is None:
            raise RuntimeError("not holding an item")
        if where == "turntable":
            spot = TURNTABLE + np.array([0, 0, TURNTABLE_TOP + ITEM_RADIUS + 0.004])
        elif where in BINS:
            spot = BINS[where] + np.array([0, 0, ITEM_RADIUS + 0.004])
        else:
            raise ValueError(f"unknown place: {where}")
        above = spot + np.array([0, 0, HOVER])
        self.move_tool(above)
        self.move_tool(spot + np.array([0, 0, ITEM_RADIUS * 0.6]), 0.8)
        i, self.held = self.held, None
        self.set_gripper(True)
        self.data.mocap_pos[self.mocap[i]] = spot
        if where == "turntable":
            self.on_table = i
        self.where[i] = where
        self.move_tool(above, 0.8)

    def rotate_turntable(self, degrees: float) -> None:
        self.table_angle += np.radians(degrees)
        self.data.ctrl[self.table_ctrl] = self.table_angle
        self.run(0.8)
