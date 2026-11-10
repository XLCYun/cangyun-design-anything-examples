import json
import shutil
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from scripts.prepare_submission import InvalidSubmission, check_url, prepare


PNG_LINK = "https://github.com/user-attachments/assets/ef752980-60ef-4c00-a4b4-987654321abc"
WEBP_LINK = "https://raw.githubusercontent.com/contributor/styles/main/overview.webp"
JSON_LINK = "https://github.com/user-attachments/files/12345/example.json"
SCHEMA = Path(__file__).resolve().parents[1] / "schemas/example.schema.json"


def image_bytes(format_name):
    stream = BytesIO()
    Image.new("RGB", (20, 10), "red").save(stream, format=format_name)
    return stream.getvalue()


def issue_body(*, metadata=""):
    return f"""### 类别

ppt

### 风格名称

俄国构成主义

### 风格目录名

russian-constructivism

### 示例名称

大学介绍

### 示例说明

用红色楔形突出年份。

### 作者

contributor

### 示例许可

CC-BY-4.0

### 参考来源

El Lissitzky https://example.com/reference Public Domain

### 预览图片

<img width="1280" alt="封面" src="{PNG_LINK}" />
![第二张]({WEBP_LINK})

### 示例元数据

{metadata}

### 公开确认

- [x] 我确认这些材料可以公开。
"""


class SubmissionTest(unittest.TestCase):
    def setUp(self):
        staging = TemporaryDirectory()
        self.addCleanup(staging.cleanup)
        self.root = Path(staging.name)
        (self.root / "schemas").mkdir()
        shutil.copy(SCHEMA, self.root / "schemas" / SCHEMA.name)
        self.assets = {
            PNG_LINK: image_bytes("PNG"),
            WEBP_LINK: image_bytes("WEBP"),
        }
        self.calls = []

    def fetch(self, url, kind, limit):
        check_url(url, kind)
        self.calls.append((kind, url))
        data = self.assets[url]
        self.assertLessEqual(len(data), limit)
        return data

    def prepare(self, body):
        event = {"issue": {"number": 42, "title": "[风格投稿] 大学介绍", "body": body}}
        return self.root / prepare(event, self.root, self.fetch)

    def json_metadata(self):
        return {
            "title": "Campus intro",
            "description": "大学介绍页",
            "author": "contributor",
            "license": "CC-BY-4.0",
            "images": [
                {"file": "images/cover.png", "caption": "封面"},
                {"file": "images/body.webp", "caption": "正文"},
            ],
        }

    def test_form_images_follow_uploaded_order(self):
        directory = self.prepare(issue_body(metadata="_No response_").replace("\n", "\r\n"))
        self.assertEqual(
            directory.relative_to(self.root).as_posix(),
            "examples/ppt/russian-constructivism/example-42",
        )
        metadata = json.loads((directory / "example.json").read_text())
        self.assertEqual(metadata["style"], "俄国构成主义")
        self.assertEqual(metadata["images"][0]["file"], "images/01.png")
        self.assertEqual(metadata["images"][1]["file"], "images/02.webp")
        self.assertEqual(metadata["references"][0]["url"], "https://example.com/reference")
        self.assertEqual((directory / "images/01.png").read_bytes(), self.assets[PNG_LINK])
        self.assertEqual((directory / "images/02.webp").read_bytes(), self.assets[WEBP_LINK])

    def test_inline_json_preserves_captions_and_filenames(self):
        expected = self.json_metadata()
        fence = "\x60" * 3
        directory = self.prepare(issue_body(metadata=f"{fence}json\n{json.dumps(expected)}\n{fence}"))
        actual = json.loads((directory / "example.json").read_text())
        self.assertEqual(actual["images"], expected["images"])
        self.assertEqual(directory.name, "campus-intro-42")
        self.assertEqual(actual["$schema"], "../../../../schemas/example.schema.json")

    def test_attached_json(self):
        self.assets[JSON_LINK] = json.dumps(self.json_metadata()).encode()
        self.prepare(issue_body(metadata=f"[example.json]({JSON_LINK})"))
        self.assertEqual(self.calls[0], ("metadata", JSON_LINK))

    def test_unconfirmed_submission_stops_before_download(self):
        with self.assertRaisesRegex(InvalidSubmission, "公开确认"):
            self.prepare(issue_body().replace("- [x]", "- [ ]"))
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "examples").exists())

    def test_metadata_cannot_escape_the_example_directory(self):
        metadata = self.json_metadata()
        metadata["images"][0]["file"] = "../workflow.png"
        with self.assertRaisesRegex(InvalidSubmission, "JSON Schema"):
            self.prepare(issue_body(metadata=json.dumps(metadata)))
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "examples").exists())

    def test_broken_second_image_does_not_write_a_partial_example(self):
        self.assets[WEBP_LINK] = b"<html>not an image</html>"
        with self.assertRaisesRegex(InvalidSubmission, "第 2 张"):
            self.prepare(issue_body())
        self.assertFalse((self.root / "examples").exists())

    def test_attachment_redirect_rejects_unapproved_destinations(self):
        for url in (
            "http://raw.githubusercontent.com/contributor/styles/main/cover.png",
            "https://raw.githubusercontent.com@127.0.0.1/cover.png",
            "https://raw.githubusercontent.com:8080/contributor/styles/main/cover.png",
            "https://example.com/cover.png",
        ):
            with self.subTest(url=url), self.assertRaises(InvalidSubmission):
                check_url(url, "image", redirected=True)
        check_url("https://private-user-images.githubusercontent.com/123/cover.png", "image", redirected=True)
        with self.assertRaises(InvalidSubmission):
            check_url("https://private-user-images.githubusercontent.com/123/cover.png", "image")


if __name__ == "__main__":
    unittest.main()
