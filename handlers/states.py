from aiogram.fsm.state import State, StatesGroup


class TrimStates(StatesGroup):
    waiting_start = State()
    waiting_end = State()


class WatermarkStates(StatesGroup):
    waiting_text = State()
    waiting_logo = State()


class BatchStates(StatesGroup):
    collecting = State()
