"""Directory-based related reading; a link is not a historical proof claim."""
from services import shiji_reader
from services.courses.textbooks import load_textbooks


def lesson_destinations() -> list[dict]:
    return [{"value": f"{book.course_id}/{lesson.lesson_id}",
             "label": f"{lesson.lesson_no} · {lesson.title}",
             "courseId": book.course_id, "lessonId": lesson.lesson_id}
            for book in load_textbooks().values() for lesson in book.lessons]


def related_reading(lesson_id: str) -> list[dict]:
    text = next((lesson for book in load_textbooks().values() for lesson in book.lessons
                 if lesson.lesson_id == lesson_id), None)
    if text is None:
        raise KeyError(lesson_id)
    words = {person.name for person in text.people} | {keyword.word for keyword in text.keywords}
    wanted = {word for word in words if len(word) >= 2}
    # Historical alternate names bridge teacher vocabulary and actual book titles.
    for names, title in (({"禹", "大禹", "夏朝"}, "夏本纪"), ({"商鞅", "卫鞅"}, "商君列传")):
        if words & names:
            wanted.add(title)
    body = "\n".join(text.body)
    links = []
    for volume in shiji_reader.navigation()["volumes"]:
        title = volume["title"]
        stem = title.split("第")[0]
        if volume["chapters"] and (any(word in title for word in wanted) or f"《{stem}》" in body):
            links.append({"title": f"《史记》卷{volume['volume_no']} · {title}",
                          "passage_id": volume["chapters"][0]["id"], "volume_no": volume["volume_no"],
                          "relation_note": "按课文人物、关键词与书目标题关联，供延伸阅读；不等于同时代现场记录。"})
    return links[:6]
