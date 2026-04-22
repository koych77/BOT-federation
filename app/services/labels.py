FEE_LABELS = {
    "entry": "Вступительный взнос",
    "membership": "Членский взнос",
    "both": "Вступительный + членский взносы",
}

APPLICATION_TYPE_LABELS = {
    "entry": "Вступление в БФБ",
    "renewal": "Продление членства",
}

ROLE_LABELS = {
    "athlete": "Спортсмен",
    "coach": "Тренер",
    "judge": "Судья",
    "representative": "Представитель",
    "other": "Другое",
}

AUTO_CHECK_LABELS = {
    "ready_for_admin_approval": "Бот проверил формальные признаки. Нужна финальная сверка админом.",
    "needs_manual_review": "Нужна ручная проверка администратором.",
    "flagged": "Есть риск или несоответствие. Нужна ручная проверка.",
}


def label(mapping: dict[str, str], value: str | None) -> str:
    if not value:
        return "-"
    return mapping.get(value, value)
