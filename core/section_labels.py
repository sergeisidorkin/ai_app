APP_SECTION_LABELS = {
    "experts": "Исполнители",
}


def get_app_section_label(section_key, default=""):
    return APP_SECTION_LABELS.get(section_key, default or section_key)
