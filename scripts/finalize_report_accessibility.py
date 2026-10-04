from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph


def set_repeat_table_headers(document: Document) -> int:
    changed = 0
    for table in document.tables:
        if not table.rows:
            continue
        tr_pr = table.rows[0]._tr.get_or_add_trPr()
        existing = tr_pr.xpath("./w:tblHeader")
        if not existing:
            marker = OxmlElement("w:tblHeader")
            marker.set(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val",
                "true",
            )
            tr_pr.append(marker)
            changed += 1
    return changed


def set_figure_alt_text(document: Document) -> int:
    body_children = list(document.element.body.iterchildren())
    changed = 0

    for index, child in enumerate(body_children):
        doc_properties = child.xpath('.//*[local-name()="docPr"]')
        if not doc_properties:
            continue

        caption = "Notebook-derived project visualization"
        for next_child in body_children[index + 1 : index + 5]:
            if next_child.tag.endswith("}p"):
                text = Paragraph(next_child, document).text.strip()
                if text.lower().startswith("figure "):
                    caption = text
                    break
                if text:
                    break
            elif next_child.tag.endswith("}tbl"):
                break

        for properties in doc_properties:
            properties.set("descr", caption)
            properties.set("title", caption[:250])
            changed += 1

    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_docx", type=Path)
    parser.add_argument("output_docx", type=Path)
    args = parser.parse_args()

    document = Document(args.input_docx)
    headers = set_repeat_table_headers(document)
    images = set_figure_alt_text(document)
    document.save(args.output_docx)
    print(f"table_headers={headers} image_alt_texts={images}")


if __name__ == "__main__":
    main()
