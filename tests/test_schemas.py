import pytest

from app.schemas.upload import Board, Standard, State, Subject


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

class TestBoardEnum:
    def test_cbse_value(self):
        assert Board.CBSE.value == "CBSE"

    def test_icse_value(self):
        assert Board.ICSE.value == "ICSE"

    def test_igcse_value(self):
        assert Board.IGCSE.value == "IGCSE"

    def test_ib_value(self):
        assert Board.IB.value == "IB"

    def test_state_board_value(self):
        assert Board.STATE_BOARD.value == "State Board"

    def test_exactly_five_boards(self):
        assert len(Board) == 5

    def test_board_from_string(self):
        assert Board("CBSE") is Board.CBSE
        assert Board("State Board") is Board.STATE_BOARD

    def test_invalid_board_raises_value_error(self):
        with pytest.raises(ValueError):
            Board("UNKNOWN")


# ---------------------------------------------------------------------------
# Standard
# ---------------------------------------------------------------------------

class TestStandardEnum:
    def test_class_1_value(self):
        assert Standard.CLASS_1.value == "Class 1"

    def test_class_6_value(self):
        assert Standard.CLASS_6.value == "Class 6"

    def test_class_12_value(self):
        assert Standard.CLASS_12.value == "Class 12"

    def test_exactly_twelve_standards(self):
        assert len(Standard) == 12

    def test_all_standards_follow_class_n_pattern(self):
        for i, standard in enumerate(Standard, start=1):
            assert standard.value == f"Class {i}"

    def test_standard_from_string(self):
        assert Standard("Class 10") is Standard.CLASS_10

    def test_invalid_standard_raises_value_error(self):
        with pytest.raises(ValueError):
            Standard("Class 13")


# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------

class TestSubjectEnum:
    def test_mathematics_value(self):
        assert Subject.MATHEMATICS.value == "Mathematics"

    def test_science_value(self):
        assert Subject.SCIENCE.value == "Science"

    def test_physics_value(self):
        assert Subject.PHYSICS.value == "Physics"

    def test_chemistry_value(self):
        assert Subject.CHEMISTRY.value == "Chemistry"

    def test_biology_value(self):
        assert Subject.BIOLOGY.value == "Biology"

    def test_english_value(self):
        assert Subject.ENGLISH.value == "English"

    def test_hindi_value(self):
        assert Subject.HINDI.value == "Hindi"

    def test_history_value(self):
        assert Subject.HISTORY.value == "History"

    def test_geography_value(self):
        assert Subject.GEOGRAPHY.value == "Geography"

    def test_computer_science_value(self):
        assert Subject.COMPUTER_SCIENCE.value == "Computer Science"

    def test_economics_value(self):
        assert Subject.ECONOMICS.value == "Economics"

    def test_accountancy_value(self):
        assert Subject.ACCOUNTANCY.value == "Accountancy"

    def test_business_studies_value(self):
        assert Subject.BUSINESS_STUDIES.value == "Business Studies"

    def test_political_science_value(self):
        assert Subject.POLITICAL_SCIENCE.value == "Political Science"

    def test_sociology_value(self):
        assert Subject.SOCIOLOGY.value == "Sociology"

    def test_psychology_value(self):
        assert Subject.PSYCHOLOGY.value == "Psychology"

    def test_exactly_sixteen_subjects(self):
        assert len(Subject) == 16

    def test_subject_from_string(self):
        assert Subject("Physics") is Subject.PHYSICS

    def test_invalid_subject_raises_value_error(self):
        with pytest.raises(ValueError):
            Subject("Art")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class TestStateEnum:
    # ── States ──────────────────────────────────────────────────────────────
    def test_andhra_pradesh(self):
        assert State.ANDHRA_PRADESH.value == "Andhra Pradesh"

    def test_maharashtra(self):
        assert State.MAHARASHTRA.value == "Maharashtra"

    def test_tamil_nadu(self):
        assert State.TAMIL_NADU.value == "Tamil Nadu"

    def test_west_bengal(self):
        assert State.WEST_BENGAL.value == "West Bengal"

    def test_uttar_pradesh(self):
        assert State.UTTAR_PRADESH.value == "Uttar Pradesh"

    def test_karnataka(self):
        assert State.KARNATAKA.value == "Karnataka"

    # ── Union Territories ───────────────────────────────────────────────────
    def test_delhi(self):
        assert State.DELHI.value == "Delhi"

    def test_jammu_and_kashmir(self):
        assert State.JAMMU_AND_KASHMIR.value == "Jammu & Kashmir"

    def test_ladakh(self):
        assert State.LADAKH.value == "Ladakh"

    def test_chandigarh(self):
        assert State.CHANDIGARH.value == "Chandigarh"

    def test_puducherry(self):
        assert State.PUDUCHERRY.value == "Puducherry"

    def test_andaman_and_nicobar(self):
        assert State.ANDAMAN_AND_NICOBAR.value == "Andaman & Nicobar Islands"

    def test_lakshadweep(self):
        assert State.LAKSHADWEEP.value == "Lakshadweep"

    def test_total_count_28_states_plus_8_uts(self):
        assert len(State) == 36

    def test_state_from_string(self):
        assert State("Karnataka") is State.KARNATAKA

    def test_invalid_state_raises_value_error(self):
        with pytest.raises(ValueError):
            State("Atlantis")
