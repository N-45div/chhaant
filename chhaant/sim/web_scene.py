"""The simulated cell as data a browser can draw with three.js.

* ``scene_geoms``: every visible geom with its body, local pose, shape, size
  and colour. Visible means the groups MuJoCo's own viewer shows by default
  (0-2); the SO-101's collision meshes (3) and its red jaw parts (4) stay out.
* ``scene_meshes``: the arm's meshes, simplified for the web by vertex
  clustering (vertices within ``cell`` metres merge). The SO-101 visual
  meshes are ~205k vertices and ~410k triangles raw; clustering at 2 mm keeps
  the shape at a fraction of the size.
* The twin streams, per frame, the world pose of each moving body; the browser
  places every geom as body pose x geom local pose.

Positions are in metres, z up; quaternions are MuJoCo's (w, x, y, z).
"""

import base64

import mujoco
import numpy as np

VISIBLE_GROUPS = (0, 1, 2)
KINDS = {
    mujoco.mjtGeom.mjGEOM_PLANE: "plane", mujoco.mjtGeom.mjGEOM_SPHERE: "sphere",
    mujoco.mjtGeom.mjGEOM_CAPSULE: "capsule", mujoco.mjtGeom.mjGEOM_ELLIPSOID: "ellipsoid",
    mujoco.mjtGeom.mjGEOM_CYLINDER: "cylinder", mujoco.mjtGeom.mjGEOM_BOX: "box", mujoco.mjtGeom.mjGEOM_MESH: "mesh",
}


def simplify(verts: np.ndarray, faces: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """Vertex clustering: snap vertices to a ``cell``-metre grid, merge, drop collapsed triangles."""
    keys, inverse = np.unique(np.floor(verts / cell).astype(np.int64), axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    merged = np.zeros((len(keys), 3))
    np.add.at(merged, inverse, verts)
    merged /= np.bincount(inverse)[:, None]
    f = inverse[faces]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    _, first = np.unique(np.sort(f, axis=1), axis=0, return_index=True)  # drop duplicates, keep winding
    return merged.astype(np.float32), f[np.sort(first)].astype(np.uint32)


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def _rgba(model, g: int) -> list[float]:
    mat = model.geom_matid[g]
    rgba = model.mat_rgba[mat] if mat >= 0 else model.geom_rgba[g]
    return [round(float(x), 3) for x in rgba]


def visible_geoms(model) -> list[int]:
    return [g for g in range(model.ngeom) if model.geom_group[g] in VISIBLE_GROUPS
            and int(model.geom_type[g]) in KINDS and _rgba(model, g)[3] > 0]


def scene_geoms(model) -> list[dict]:
    out = []
    for g in visible_geoms(model):
        kind = KINDS[int(model.geom_type[g])]
        entry = {"body": int(model.geom_bodyid[g]), "type": kind, "size": [round(float(s), 5) for s in model.geom_size[g]],
                 "rgba": _rgba(model, g), "pos": [round(float(p), 5) for p in model.geom_pos[g]],
                 "quat": [round(float(q), 5) for q in model.geom_quat[g]]}
        if kind == "mesh":
            entry["mesh"] = int(model.geom_dataid[g])
        out.append(entry)
    return out


def scene_meshes(model, cell: float = 0.002) -> dict:
    meshes = {}
    for g in visible_geoms(model):
        if int(model.geom_type[g]) != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mid = int(model.geom_dataid[g])
        if str(mid) in meshes:
            continue
        v0, nv = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
        f0, nf = model.mesh_faceadr[mid], model.mesh_facenum[mid]
        v, f = simplify(np.asarray(model.mesh_vert[v0:v0 + nv], float), np.asarray(model.mesh_face[f0:f0 + nf]), cell)
        meshes[str(mid)] = {"v": _b64(v), "f": _b64(f), "nv": int(len(v)), "nf": int(len(f))}
    return meshes
