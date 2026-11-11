import argparse
import json
import re
import shutil
from html import escape
from pathlib import Path
from string import Template
from tempfile import TemporaryDirectory
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"ppt": "PPT", "ui": "网页 UI", "paper": "论文插图"}


def render_license(license_name):
    text = escape(license_name)
    cc = re.fullmatch(r"CC-(BY(?:-NC)?(?:-SA|-ND)?)-(1\.0|2\.0|2\.5|3\.0|4\.0)", license_name)
    if cc:
        return f'<a href="https://creativecommons.org/licenses/{cc[1].lower()}/{cc[2]}/">{text}</a>'
    if license_name == "CC0-1.0":
        return f'<a href="https://creativecommons.org/publicdomain/zero/1.0/">{text}</a>'
    return text


def render_references(references):
    if not references:
        return ""
    items = []
    for reference in references:
        url = escape(reference["url"])
        title = escape(reference.get("title", reference["url"]))
        credit = escape(reference.get("credit", ""))
        note = f'<p class="source-credit">{credit}</p>' if credit else ""
        items.append(f'<li><a href="{url}">{title}</a>{note}</li>')
    links = "\n".join(items)
    return f'<section class="references"><h2>参考来源</h2><ul>{links}</ul></section>'


def build_example(metadata_path, output, category, validator, template):
    example_dir = metadata_path.parent
    relative_dir = example_dir.relative_to(ROOT)
    source_dir = example_dir.resolve()
    if not source_dir.is_relative_to(ROOT / "examples") or metadata_path.is_symlink():
        raise ValueError(f"示例元数据路径无效 {metadata_path.relative_to(ROOT)}")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        validator.validate(metadata)
    except (ValueError, ValidationError) as error:
        raise ValueError(f"无法读取示例元数据 {metadata_path.relative_to(ROOT)}") from error

    target_dir = output / relative_dir
    (target_dir / "images").mkdir(parents=True)
    shutil.copyfile(metadata_path, target_dir / "example.json")
    previews = []
    for image in metadata["images"]:
        source = example_dir / image["file"]
        if not source.is_file() or not source.resolve().is_relative_to(source_dir):
            raise ValueError(f"预览图路径无效 {source.relative_to(ROOT)}")
        shutil.copyfile(source, target_dir / image["file"])
        image_url = quote(image["file"])
        caption = escape(image["caption"])
        previews.append(
            f'<figure><a href="{image_url}"><img src="{image_url}" alt="{caption}" '
            f'loading="lazy" decoding="async"></a><figcaption>{caption}</figcaption></figure>'
        )

    style = metadata.get("style") or example_dir.parent.name.replace("-", " ")
    page = template.substitute(
        root="../" * len(relative_dir.parts),
        category=category,
        category_label=CATEGORIES[category],
        title=escape(metadata["title"]),
        style=escape(style),
        description=escape(metadata["description"]),
        author=escape(metadata["author"]),
        license=render_license(metadata["license"]),
        previews="\n".join(previews),
        references=render_references(metadata.get("references", [])),
    )
    (target_dir / "index.html").write_text(page, encoding="utf-8")

    entry_url = f"../{quote(relative_dir.as_posix())}/"
    return {
        "title": metadata["title"],
        "style": style,
        "description": metadata["description"],
        "cover": entry_url + quote(metadata["images"][0]["file"]),
        "detail": entry_url + "example.json",
        "page": entry_url,
    }


def build_gallery(output):
    site_dir = ROOT / "site"
    catalog_dir = output / "catalog"
    catalog_dir.mkdir(parents=True)
    for filename in ("index.html", "styles.css", "gallery.js"):
        shutil.copyfile(site_dir / filename, output / filename)

    schema_path = ROOT / "schemas" / "example.schema.json"
    (output / "schemas").mkdir()
    shutil.copyfile(schema_path, output / "schemas" / schema_path.name)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    template = Template((site_dir / "example.html").read_text(encoding="utf-8"))
    for category in CATEGORIES:
        metadata_paths = sorted((ROOT / "examples" / category).glob("*/*/example.json"))
        entries = [build_example(path, output, category, validator, template) for path in metadata_paths]
        (catalog_dir / f"{category}.json").write_text(
            json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        print(f"{category}  {len(entries)}")


def main():
    parser = argparse.ArgumentParser(description="构建示例图集和分类索引")
    parser.add_argument("output", type=Path, help="尚未存在的输出目录")
    output = parser.parse_args().output.resolve()
    if output.exists():
        parser.error(f"输出目录已存在 {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as staging:
        generated = Path(staging) / "gallery"
        build_gallery(generated)
        generated.rename(output)


if __name__ == "__main__":
    main()
