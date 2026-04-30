FEE_LABELS = {
    "entry": "Вступительный взнос",
    "membership": "Членский взнос",
    "both": "Вступительный + членский взносы",
}

APPLICATION_TYPE_LABELS = {
    "entry": "Вступление в БФБ",
    "renewal": "Продление членства",
}

APPLICANT_MODE_LABELS = {
    "self": "Заявитель",
    "child": "Заявитель за ребенка",
}

ROLE_LABELS = {
    "member": "Член федерации",
    "presidium": "Член Президиума",
    "dancer": "Танцор",
    "trainer": "Тренер",
    "veteran": "Ветеран",
    "organizer": "Организатор",
    "dj": "Ди-джей",
    "mc": "МС",
    "photo_video": "Фото-видео",
    "other": "Иное",
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
