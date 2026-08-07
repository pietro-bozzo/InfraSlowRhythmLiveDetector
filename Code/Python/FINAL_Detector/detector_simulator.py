""" Simulator of Infra-Slow Activity live detector that bypasses Open Ephys """

# only line that should be modified per run:
CONFIG_PATH = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/FINAL_Detector/CONFIGS/Hubel_tests/CONFIG_Karadoc_0305.py"
# =============================================================================

from Detector_final import ISDetector, PyProcessor

# =============================================================================
# MockProcessor : replaces `processor` argument in PyProcessor (usually given by OE)
# =============================================================================
class MockProcessor:
    def add_python_event(self,a,b):
        print(f'added python event: {a}, {b}')
        return