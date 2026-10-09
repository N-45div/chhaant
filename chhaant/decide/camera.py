"""Connect the inspection policy to the cell: rotate, photograph, segment, score.

``TurntableCamera`` turns the policy's "look at 135 degrees" into a turntable
move, a photo, a segmentation and a quality-model reading. With
``VirtualTurntable`` the photos are TR-6's real ones; the same adapter serves
a live turntable.
"""

from chhaant.decide.policy import Look
from chhaant.vision.segment import segment_fruit


class TurntableCamera:
    def __init__(self, turntable, model):
        self.turntable = turntable
        self.model = model  # anything with .predict(bgr, mask) -> reading with .defect and .ripeness

    def _score(self, capture) -> Look:
        seg = segment_fruit(capture.image)
        reading = self.model.predict(capture.image, seg.mask if seg.ok else None)
        return Look(capture.azimuth, capture.elevation, reading.defect, reading.ripeness, capture.source)

    def look_down(self) -> Look:
        return self._score(self.turntable.capture_top())

    def look_at(self, azimuth: float) -> Look:
        self.turntable.rotate_to(azimuth)
        return self._score(self.turntable.capture())
