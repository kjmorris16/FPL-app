"""Scale attacking output / defensive workload by FPL's own fixture difficulty rating."""
from src.scoring import constants as c


def attacking_multiplier(difficulty: int) -> float:
    """Easier fixture (low difficulty) boosts expected goals/assists."""
    return 1 + (c.FIXTURE_DIFFICULTY_NEUTRAL - difficulty) * c.FIXTURE_DIFFICULTY_SLOPE


def defensive_shots_multiplier(difficulty: int) -> float:
    """Harder fixture (facing a stronger attack) means more shots faced, more saves."""
    return 1 + (difficulty - c.FIXTURE_DIFFICULTY_NEUTRAL) * c.FIXTURE_DIFFICULTY_SLOPE
