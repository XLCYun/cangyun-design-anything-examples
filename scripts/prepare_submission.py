import hashlib
import html
import json
import re
import sys
import unicodedata
from http.client import HTTPException
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image


PREFIX = "[风格投稿]"
CATEGORIES = {"ppt", "ui", "paper"}
FIELD_NAMES = {
    "类别", "风格名称", "风格目录名", "示例名称", "预览图片", "示例说明",
    "作者", "示例许可", "参考来源", "生成提示词", "示例元数据", "公开确认",
}
EXTENSIONS = {"PNG": (".png",), "JPEG": (".jpg", ".jpeg"), "WEBP": (".webp",)}
MAX_IMAGES = 10
MAX_IMAGE_BYTES = 10 * 1024**2
MAX_TOTAL_BYTES = 32 * 1024**2
MAX_METADATA_BYTES = 64 * 1024
URL_PATTERN = re.compile(r"https?://[^\s<>\x22\x27)\]]+")
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ATTACHMENT_PATH = re.compile(r"/user-attachments/assets/[0-9a-fA-F-]{36}")
FILE_PATH = re.compile(r"/user-attachments/files/[0-9]+/[^/]+")
REDIRECT_HOSTS = {
    "private-user-images.githubusercontent.com",
    "objects.githubusercontent.com",
    "media.githubusercontent.com",
    "github-production-user-asset-6210df.s3.amazonaws.com",
    "github-production-repository-file-5c1aeb.s3.amazonaws.com",
}


class InvalidSubmission(ValueError):
    pass


def split_fields(body):
    body = body.replace("\r\n", "\n")
    headings = [
        heading
        for heading in re.finditer(r"^### ([^\r\n]+)$", body, re.MULTILINE)
        if heading[1].strip() in FIELD_NAMES
    ]
    fields = {}
    for index, heading in enumerate(headings):
        name = heading[1].strip()
        if name in fields:
            raise InvalidSubmission(f"重复字段「{name}」")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        value = body[heading.end():end].strip()
        fields[name] = "" if value == "_No response_" else value
    return fields


def required(fields, name):
    value = fields.get(name, "")
    if not value:
        raise InvalidSubmission(f"请填写「{name}」")
    return value


def urls_in(text):
    return list(dict.fromkeys(html.unescape(url) for url in URL_PATTERN.findall(text)))


def check_url(url, kind, *, redirected=False):
    parts = urlsplit(url)
    if (
        parts.scheme != "https" or parts.username is not None or parts.password is not None
        or parts.port not in (None, 443) or parts.fragment
        or any(character.isspace() for character in url)
    ):
        raise InvalidSubmission("附件必须使用允许的 GitHub HTTPS 链接")

    host = parts.hostname
    path = parts.path
    if host == "github.com":
        allowed_suffixes = (".json",) if kind == "metadata" else (".webp", ".png", ".jpg", ".jpeg")
        if FILE_PATH.fullmatch(path) and path.lower().endswith(allowed_suffixes):
            return
        if kind == "image" and ATTACHMENT_PATH.fullmatch(path):
            return
    if host == "raw.githubusercontent.com" and path.count("/") >= 4:
        return
    if kind == "image" and host == "user-images.githubusercontent.com" and path.count("/") >= 2:
        return
    if redirected and host in REDIRECT_HOSTS:
        return
    raise InvalidSubmission("请使用 GitHub Issue 附件或公开的 raw.githubusercontent.com 链接")


class AttachmentRedirects(HTTPRedirectHandler):
    def __init__(self, kind):
        self.kind = kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.kind, redirected=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, kind, limit):
    check_url(url, kind)
    opener = build_opener(AttachmentRedirects(kind))
    request = Request(url, headers={"User-Agent": "Design-Anything-Style-Submission"})
    try:
        with opener.open(request, timeout=15) as response:
            size = response.headers.get("Content-Length", "")
            if size.isdecimal() and int(size) > limit:
                raise InvalidSubmission("附件超过大小限制")
            data = response.read(limit + 1)
    except (OSError, HTTPException) as error:
        raise InvalidSubmission("附件无法下载，请检查链接是否可公开读取") from error
    if not data or len(data) > limit:
        raise InvalidSubmission("附件为空或超过大小限制")
    return data


def image_extensions(data):
    try:
        with Image.open(BytesIO(data), formats=list(EXTENSIONS)) as image:
            if max(image.size) > 4096:
                raise InvalidSubmission("预览图最长边应在 4096 像素以内")
            extensions = EXTENSIONS[image.format]
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise InvalidSubmission("预览图须为可读取的 PNG、JPEG 或 WebP") from error
    return extensions


def read_metadata(value, fetch):
    if not value:
        return None
    fenced = re.fullmatch(r"\x60{3}(?:json)?[ \t]*\r?\n(.*?)\r?\n\x60{3}", value, re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced[1]
    elif not value.startswith("{"):
        links = urls_in(value)
        if len(links) != 1:
            raise InvalidSubmission("「示例元数据」需要一个 JSON 对象或一个 example.json 链接")
        value = fetch(links[0], "metadata", MAX_METADATA_BYTES).decode("utf-8-sig")
    if len(value.encode("utf-8")) > MAX_METADATA_BYTES:
        raise InvalidSubmission("示例元数据超过 64 KiB")
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError as error:
        raise InvalidSubmission("「示例元数据」不是有效的 JSON") from error
    if not isinstance(metadata, dict):
        raise InvalidSubmission("「示例元数据」需要一个 JSON 对象")
    return metadata


def metadata_from_form(fields):
    metadata = {
        "title": required(fields, "示例名称"),
        "description": required(fields, "示例说明"),
        "author": required(fields, "作者"),
        "license": required(fields, "示例许可"),
        "images": [],
    }
    references = [
        {"url": url, "credit": line.strip()}
        for line in fields.get("参考来源", "").splitlines()
        for url in urls_in(line)
    ]
    if references:
        metadata["references"] = references
    if fields.get("生成提示词"):
        metadata["prompt"] = fields["生成提示词"]
    return metadata


def slug(text, fallback):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:60].rstrip("-") or fallback


def validate(metadata, validator):
    error = next(validator.iter_errors(metadata), None)
    if error is not None:
        field = ".".join(map(str, error.absolute_path)) or "example.json"
        raise InvalidSubmission(f"{field} 未通过 JSON Schema 校验")
    if any(not metadata[key].strip() for key in ("title", "description", "author", "license")):
        raise InvalidSubmission("标题、说明、作者和示例许可需要有效文字")
    filenames = [image["file"] for image in metadata["images"]]
    if len(filenames) != len(set(filenames)):
        raise InvalidSubmission("元数据里的图片文件名需要各不相同")


def prepare(event, root, fetch=download):
    root = root.resolve()
    issue = event["issue"]
    issue_number = issue["number"]
    if not issue["title"].startswith(PREFIX) or type(issue_number) is not int or issue_number < 1:
        raise InvalidSubmission("需要一个带有 [风格投稿] 前缀的 Issue")
    fields = split_fields(issue.get("body") or "")
    if not re.search(r"^-\s*\[[xX]\]\s+\S", fields.get("公开确认", ""), re.MULTILINE):
        raise InvalidSubmission("请勾选「公开确认」")
    category = required(fields, "类别")
    if category not in CATEGORIES:
        raise InvalidSubmission("类别必须是 ppt、ui 或 paper")
    style = required(fields, "风格名称")
    style_dir = fields.get("风格目录名", "")
    if style_dir and (len(style_dir) > 60 or not SLUG_PATTERN.fullmatch(style_dir)):
        raise InvalidSubmission("风格目录名使用小写英文字母、数字和连字符，最多 60 字符")
    if not style_dir:
        style_key = unicodedata.normalize("NFKC", style).casefold().encode("utf-8")
        style_dir = slug(style, "style-" + hashlib.sha256(style_key).hexdigest()[:10])

    links = urls_in(required(fields, "预览图片"))
    if not 1 <= len(links) <= MAX_IMAGES:
        raise InvalidSubmission("请在「预览图片」放入 1 至 10 张图片链接")
    schema = json.loads((root / "schemas/example.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    supplied = read_metadata(fields.get("示例元数据", ""), fetch)
    metadata = supplied if supplied is not None else metadata_from_form(fields)
    metadata["$schema"] = "../../../../schemas/example.schema.json"
    metadata.setdefault("style", style)
    if supplied is not None:
        validate(metadata, validator)
        if len(metadata["images"]) != len(links):
            raise InvalidSubmission("元数据图片列表须与「预览图片」的数量、顺序一致")
        if "sourceFiles" in metadata:
            raise InvalidSubmission("可编辑源文件请通过人工 PR 提交")

    name = slug(metadata["title"], "example")
    relative_path = Path("examples") / category / style_dir / f"{name}-{issue_number}"
    destination = root / relative_path
    if destination.exists() or not destination.resolve().is_relative_to(root / "examples"):
        raise InvalidSubmission("示例目录已存在或路径无效")

    images = []
    total_size = 0
    for index, url in enumerate(links):
        try:
            data = fetch(url, "image", min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - total_size))
            total_size += len(data)
            extensions = image_extensions(data)
        except InvalidSubmission as error:
            raise InvalidSubmission(f"第 {index + 1} 张预览图 {error}") from error
        if supplied is None:
            filename = f"images/{index + 1:02d}{extensions[0]}"
            caption = "封面" if index == 0 else f"预览图 {index + 1}"
            metadata["images"].append({"file": filename, "caption": caption})
        filename = metadata["images"][index]["file"]
        if Path(filename).suffix not in extensions:
            raise InvalidSubmission(f"第 {index + 1} 张图的文件扩展名与实际格式不一致")
        images.append((filename, data))
    validate(metadata, validator)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as staging:
        staged = Path(staging) / "example"
        (staged / "images").mkdir(parents=True)
        for filename, data in images:
            (staged / filename).write_bytes(data)
        (staged / "example.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        staged.rename(destination)
    return relative_path


def main():
    event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        print(prepare(event, Path.cwd()).as_posix())
    except ValueError as error:
        message = " ".join(str(error).splitlines())[:500]
        print(f"投稿校验失败 {message}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
