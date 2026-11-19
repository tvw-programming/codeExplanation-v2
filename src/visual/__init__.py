"""Visual graph / lifecycle / interactive packaging for CEV.

Honesty first: never invent edges for stacks whose extractors are
placeholder or empty-valid. Shipped slices: React, Go Fiber.
"""

from .pipeline import attach_visuals, build_visual_artifacts

__all__ = ["attach_visuals", "build_visual_artifacts"]
