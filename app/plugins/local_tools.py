from __future__ import annotations

import csv
import html
import json
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import requests

from app.plugins.base import Artifact, Plugin, ToolDefinition, ToolResult
from app.plugins.utils import approved_path, artifact_path, validate_public_url
from config import DATA_DIR, TAVILY_API_KEY


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


class DocumentsPlugin(Plugin):
    id, name = "documents", "Documents"
    description = "Create professionally formatted Word documents."
    permissions = ["create local documents"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_document", "Create a formatted DOCX document from a title and sections.", _object({
            "filename": {"type": "string"}, "title": {"type": "string"},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "heading": {"type": "string"}, "paragraphs": {"type": "array", "items": {"type": "string"}},
                "bullets": {"type": "array", "items": {"type": "string"}}
            }}},
        }, ["title", "sections"]), self.create_document)]

    def create_document(self, title: str, sections: list[dict], filename: str = "document.docx") -> ToolResult:
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Inches, Pt
            path = artifact_path(filename, "document.docx", "docx")
            doc = Document()
            section = doc.sections[0]
            section.top_margin = section.bottom_margin = Inches(0.75)
            section.left_margin = section.right_margin = Inches(0.85)
            styles = doc.styles
            styles["Normal"].font.name, styles["Normal"].font.size = "Aptos", Pt(10.5)
            heading = doc.add_heading(title, 0)
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for item in sections:
                section_heading = item.get("heading") or item.get("title")
                if section_heading and str(section_heading).strip() != str(title).strip():
                    doc.add_heading(str(section_heading), level=1)
                paragraphs = item.get("paragraphs") or []
                if not paragraphs and item.get("content"):
                    paragraphs = [line.strip() for line in str(item["content"]).splitlines() if line.strip()]
                for paragraph in paragraphs:
                    doc.add_paragraph(str(paragraph))
                for bullet in item.get("bullets") or []:
                    doc.add_paragraph(str(bullet), style="List Bullet")
            doc.save(path)
            return ToolResult(True, self.id, "create_document", artifacts=[Artifact(path.name, str(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")], message="Word document created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_document", error=str(exc), message="Document creation failed")


class SpreadsheetsPlugin(Plugin):
    id, name = "spreadsheets", "Spreadsheets"
    description = "Create presentation-ready Excel workbooks from structured data."
    permissions = ["create and read local spreadsheets"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_excel", "Create a formatted XLSX workbook. Rows may be arrays or objects.", _object({
            "filename": {"type": "string"}, "sheet_name": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {}},
            "chart": {"type": "object", "description": "Optional chart: {type,title,category_column,value_column}"}
        }, ["headers", "rows"]), self.create_excel)]

    def create_excel(self, headers: list[str], rows: list[Any], filename: str = "workbook.xlsx", sheet_name: str = "Data", chart: dict | None = None) -> ToolResult:
        try:
            from openpyxl import Workbook
            from openpyxl.chart import BarChart, LineChart, PieChart, Reference
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.worksheet.table import Table, TableStyleInfo
            from openpyxl.utils import get_column_letter
            path = artifact_path(filename, "workbook.xlsx", "xlsx")
            wb, ws = Workbook(), None
            ws = wb.active
            ws.title = (sheet_name or "Data")[:31]
            ws.append(headers)
            normalized = [[row.get(h, "") for h in headers] if isinstance(row, dict) else list(row) for row in rows]
            for row in normalized:
                ws.append(row[:len(headers)] + [""] * max(0, len(headers) - len(row)))
            fill = PatternFill("solid", fgColor="1F4E78")
            for cell in ws[1]:
                cell.fill, cell.font, cell.alignment = fill, Font(color="FFFFFF", bold=True), Alignment(horizontal="center")
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            if headers and normalized:
                table = Table(displayName="DataTable", ref=ws.dimensions)
                table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False)
                ws.add_table(table)
            for index, header in enumerate(headers, 1):
                values = [str(header)] + [str(row[index - 1]) if index <= len(row) else "" for row in normalized[:200]]
                ws.column_dimensions[get_column_letter(index)].width = min(45, max(10, max(map(len, values)) + 2))
            if chart and normalized:
                chart_cls = {"line": LineChart, "pie": PieChart}.get(str(chart.get("type", "bar")).lower(), BarChart)
                graph = chart_cls()
                graph.title = chart.get("title") or "Chart"
                cat_col = max(1, int(chart.get("category_column", 1)))
                val_col = max(1, int(chart.get("value_column", 2)))
                graph.add_data(Reference(ws, min_col=val_col, min_row=1, max_row=ws.max_row), titles_from_data=True)
                graph.set_categories(Reference(ws, min_col=cat_col, min_row=2, max_row=ws.max_row))
                ws.add_chart(graph, f"{get_column_letter(len(headers) + 2)}2")
            wb.save(path)
            return ToolResult(True, self.id, "create_excel", artifacts=[Artifact(path.name, str(path), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")], message="Excel workbook created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_excel", error=str(exc), message="Spreadsheet creation failed")


class PresentationsPlugin(Plugin):
    id, name = "presentations", "Presentations"
    description = "Create designed 16:9 PowerPoint decks with strong typography and varied editorial layouts."
    permissions = ["create local presentations"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_presentation", "Create a polished PPTX from a title and concise narrative slide plan. Use takeaway-style slide titles and no more than five short bullets per slide.", _object({
            "filename": {"type": "string"}, "title": {"type": "string"}, "subtitle": {"type": "string"},
            "theme": {"type": "string", "enum": ["midnight", "ocean", "ember"], "description": "Built-in visual theme; midnight is the default."},
            "template_name": {"type": "string", "description": "Optional reusable template preset created by Template Creator."},
            "slides": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "bullets"]}}
        }, ["title", "slides"]), self.create_presentation)]

    def create_presentation(self, title: str, slides: list[dict], filename: str = "presentation.pptx", subtitle: str = "", theme: str = "midnight", template_name: str = "") -> ToolResult:
        try:
            from pptx import Presentation
            from pptx.dml.color import RGBColor
            from pptx.enum.shapes import MSO_SHAPE
            from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
            from pptx.util import Inches, Pt

            palettes = {
                "midnight": {"dark": "080D1C", "light": "F4F7FB", "accent": "00C8FF", "accent2": "7B61FF", "ink": "10182A"},
                "ocean": {"dark": "062A38", "light": "EFFAFA", "accent": "18D1C5", "accent2": "0B7FAB", "ink": "073240"},
                "ember": {"dark": "24100D", "light": "FFF6EF", "accent": "FF5A36", "accent2": "FFB000", "ink": "32140E"},
            }
            if template_name:
                safe_template = re.sub(r"[^a-z0-9_-]+", "-", template_name.lower()).strip("-")
                template_path = DATA_DIR / "presentation_templates" / f"{safe_template}.json"
                if not template_path.is_file():
                    raise ValueError(f"Presentation template '{template_name}' was not found")
                template_data = json.loads(template_path.read_text(encoding="utf-8"))
                theme = str(template_data.get("theme") or theme)
            palette = palettes.get(str(theme).lower(), palettes["midnight"])
            rgb = lambda value: RGBColor.from_string(value)

            def add_rect(slide, left, top, width, height, color, radius=False):
                shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
                shape = slide.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
                shape.fill.solid(); shape.fill.fore_color.rgb = rgb(color)
                shape.line.fill.background()
                return shape

            def add_text(slide, text, left, top, width, height, size, color, bold=False, font="Aptos Display", align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
                box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
                frame = box.text_frame
                frame.clear(); frame.word_wrap = True; frame.vertical_anchor = valign
                frame.margin_left = frame.margin_right = 0
                frame.margin_top = frame.margin_bottom = 0
                paragraph = frame.paragraphs[0]
                paragraph.text = str(text)
                paragraph.alignment = align
                paragraph.font.name = font; paragraph.font.size = Pt(size); paragraph.font.bold = bold; paragraph.font.color.rgb = rgb(color)
                return box

            path = artifact_path(filename, "presentation.pptx", "pptx")
            prs = Presentation()
            prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

            # Minimal cinematic opener.
            first = prs.slides.add_slide(prs.slide_layouts[6])
            first.background.fill.solid(); first.background.fill.fore_color.rgb = rgb(palette["dark"])
            add_rect(first, 0, 0, 13.333, 0.12, palette["accent"])
            add_rect(first, 10.85, 0.12, 2.483, 7.38, palette["accent2"])
            add_rect(first, 10.55, 5.85, 2.783, 0.18, palette["accent"])
            add_text(first, "E.D.I.T.H.  /  WORK MODE", 0.85, 0.68, 5.8, 0.35, 13, palette["accent"], True)
            add_text(first, title, 0.82, 1.55, 8.9, 2.4, 54, "F7FAFF", True)
            if subtitle:
                add_text(first, subtitle, 0.88, 4.25, 8.0, 1.0, 23, "B8C5DA")
            add_text(first, "PRESENTATION", 0.88, 6.6, 2.4, 0.3, 12, "8796AF", True)

            for slide_index, item in enumerate(slides, start=1):
                slide = prs.slides.add_slide(prs.slide_layouts[6])
                is_dark = slide_index % 3 != 2
                background = palette["dark"] if is_dark else palette["light"]
                title_color = "F7FAFF" if is_dark else palette["ink"]
                body_color = "C3CDDE" if is_dark else "38445A"
                slide.background.fill.solid(); slide.background.fill.fore_color.rgb = rgb(background)

                if slide_index % 3 == 1:
                    add_rect(slide, 0, 0, 0.15, 7.5, palette["accent"])
                    add_text(slide, f"{slide_index:02d}", 0.72, 0.6, 1.0, 0.45, 18, palette["accent"], True)
                    add_text(slide, str(item.get("title") or ""), 0.72, 1.22, 11.5, 1.2, 36, title_color, True)
                    bullet_left, bullet_top, bullet_width = 0.9, 2.75, 10.8
                elif slide_index % 3 == 2:
                    add_rect(slide, 0, 0, 3.35, 7.5, palette["accent2"])
                    add_text(slide, f"{slide_index:02d}", 0.65, 0.62, 1.0, 0.45, 18, "FFFFFF", True)
                    add_text(slide, str(item.get("title") or ""), 0.65, 1.35, 2.25, 3.5, 35, "FFFFFF", True)
                    bullet_left, bullet_top, bullet_width = 4.05, 1.15, 8.15
                else:
                    add_rect(slide, 0.75, 0.62, 1.15, 0.1, palette["accent"])
                    add_text(slide, str(item.get("title") or ""), 0.75, 1.0, 8.9, 1.25, 36, title_color, True)
                    add_text(slide, f"{slide_index:02d}", 10.85, 0.62, 1.3, 0.7, 30, palette["accent"], True, align=PP_ALIGN.RIGHT)
                    bullet_left, bullet_top, bullet_width = 0.95, 2.6, 11.25

                bullets = [str(value).strip() for value in (item.get("bullets") or []) if str(value).strip()][:5]
                for bullet_index, bullet in enumerate(bullets):
                    y = bullet_top + bullet_index * 0.82
                    marker_color = palette["accent"] if bullet_index % 2 == 0 else palette["accent2"]
                    add_rect(slide, bullet_left, y + 0.08, 0.42, 0.42, marker_color, radius=True)
                    add_text(slide, str(bullet_index + 1), bullet_left, y + 0.075, 0.42, 0.42, 11, "FFFFFF", True, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
                    add_text(slide, bullet, bullet_left + 0.68, y, bullet_width - 0.68, 0.62, 20, body_color)

                footer_color = "637089" if is_dark else "7B8799"
                add_rect(slide, 0.72, 7.05, 11.9, 0.015, palette["accent"])
                add_text(slide, "E.D.I.T.H.", 0.72, 7.14, 1.4, 0.22, 10, footer_color, True)
                add_text(slide, f"{slide_index} / {len(slides)}", 11.2, 7.14, 1.4, 0.22, 10, footer_color, True, align=PP_ALIGN.RIGHT)

            prs.save(path)
            return ToolResult(True, self.id, "create_presentation", artifacts=[Artifact(path.name, str(path), "application/vnd.openxmlformats-officedocument.presentationml.presentation")], message="PowerPoint presentation created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_presentation", error=str(exc), message="Presentation creation failed")


class TemplateCreatorPlugin(Plugin):
    id, name = "template_creator", "Template Creator"
    description = "Save and reuse designed presentation presets for future Work Mode decks."
    permissions = ["create and read local presentation presets"]

    @staticmethod
    def _directory() -> Path:
        directory = DATA_DIR / "presentation_templates"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _slug(name: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", str(name).lower()).strip("-")
        if not slug: raise ValueError("Template name is required")
        return slug[:80]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("presentation_template_save", "Save a reusable presentation visual preset.", _object({"name": {"type": "string"}, "theme": {"type": "string", "enum": ["midnight", "ocean", "ember"]}, "description": {"type": "string"}}, ["name", "theme"]), self.save_template),
            ToolDefinition("presentation_template_list", "List reusable presentation visual presets.", _object({}), self.list_templates),
        ]

    def save_template(self, name: str, theme: str, description: str = "") -> ToolResult:
        try:
            if theme not in {"midnight", "ocean", "ember"}: raise ValueError("Unknown presentation theme")
            path = self._directory() / f"{self._slug(name)}.json"
            payload = {"name": name.strip(), "theme": theme, "description": description.strip()}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return ToolResult(True, self.id, "presentation_template_save", data={"template": payload}, message=f"Presentation template saved: {name}")
        except Exception as exc:
            return ToolResult(False, self.id, "presentation_template_save", error=str(exc), message="Could not save presentation template")

    def list_templates(self) -> ToolResult:
        try:
            templates = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self._directory().glob("*.json"))]
            return ToolResult(True, self.id, "presentation_template_list", data={"templates": templates}, message=f"Found {len(templates)} presentation templates")
        except Exception as exc:
            return ToolResult(False, self.id, "presentation_template_list", error=str(exc), message="Could not list presentation templates")


class PDFPlugin(Plugin):
    id, name = "pdf", "PDF"
    description = "Create PDFs and extract text from local PDFs."
    permissions = ["create and read local PDFs"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("create_pdf", "Create a PDF report from a title and sections. Set one_page=true when the user explicitly requests a one-page report.", _object({"filename": {"type": "string"}, "title": {"type": "string"}, "sections": {"type": "array", "items": {"type": "object"}}, "one_page": {"type": "boolean"}}, ["title", "sections"]), self.create_pdf),
            ToolDefinition("extract_pdf_text", "Extract text from a PDF in the assistant data directory.", _object({"path": {"type": "string"}}, ["path"]), self.extract_pdf_text),
        ]

    def create_pdf(self, title: str, sections: list[dict], filename: str = "report.pdf", one_page: bool = False) -> ToolResult:
        try:
            import html
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer
            path = artifact_path(filename, "report.pdf", "pdf")
            def pdf_text(value: object) -> str:
                cleaned = str(value)
                for source, replacement in {
                    "•": "-", "‑": "-", "–": "-", "—": "-",
                    "✅": "[Done]", "🔄": "[In progress]", "⏳": "[Planned]",
                    "⚠️": "[Risk]", "⚠": "[Risk]",
                }.items():
                    cleaned = cleaned.replace(source, replacement)
                return html.escape(cleaned)
            styles, story = getSampleStyleSheet(), []
            if one_page:
                title_style = ParagraphStyle("CompactTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=19, spaceAfter=5)
                heading_style = ParagraphStyle("CompactHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=10.5, leading=12, spaceBefore=3, spaceAfter=1.5)
                body_style = ParagraphStyle("CompactBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=9.8, spaceAfter=1.5)
                margins, title_gap, body_gap = 34, 4, 1.5
            else:
                title_style, heading_style, body_style = styles["Title"], styles["Heading1"], styles["BodyText"]
                margins, title_gap, body_gap = 54, 18, 8
            story.extend([Paragraph(pdf_text(title), title_style), Spacer(1, title_gap)])
            for section in sections:
                section_heading = section.get("heading") or section.get("title")
                if section_heading and str(section_heading).strip() != str(title).strip():
                    story.append(Paragraph(pdf_text(section_heading), heading_style))
                paragraphs = section.get("paragraphs") or []
                if not paragraphs and section.get("content"):
                    paragraphs = [line.strip() for line in str(section["content"]).splitlines() if line.strip()]
                for text in paragraphs:
                    story.extend([Paragraph(pdf_text(text), body_style), Spacer(1, body_gap)])
            document = SimpleDocTemplate(
                str(path), pagesize=A4,
                leftMargin=margins, rightMargin=margins,
                topMargin=margins, bottomMargin=margins,
            )
            if one_page:
                usable_width = A4[0] - (2 * margins)
                usable_height = A4[1] - (2 * margins)
                document.build([KeepInFrame(usable_width, usable_height, story, mode="shrink")])
            else:
                document.build(story)
            return ToolResult(True, self.id, "create_pdf", artifacts=[Artifact(path.name, str(path), "application/pdf")], message="PDF created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_pdf", error=str(exc), message="PDF creation failed")

    def extract_pdf_text(self, path: str) -> ToolResult:
        try:
            import fitz
            source = approved_path(path)
            if source.stat().st_size > 25_000_000: raise ValueError("PDF exceeds the 25 MB limit")
            with fitz.open(source) as doc: text = "\n".join(page.get_text() for page in doc)
            return ToolResult(True, self.id, "extract_pdf_text", data={"text": text[:100_000]}, message="PDF text extracted")
        except Exception as exc:
            return ToolResult(False, self.id, "extract_pdf_text", error=str(exc), message="PDF extraction failed")


class WebPlugin(Plugin):
    id, name = "browser", "Browser"
    description = "Search the web and inspect readable public webpages for Work Mode research."
    permissions = ["access public web pages"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("web_search", "Search the public web and return structured results.", _object({"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 10}}, ["query"]), self.web_search),
            ToolDefinition("read_url", "Read and clean the visible text of a public HTTP(S) webpage.", _object({"url": {"type": "string"}}, ["url"]), self.read_url),
        ]

    def web_search(self, query: str, max_results: int = 5) -> ToolResult:
        if not TAVILY_API_KEY:
            return ToolResult(False, self.id, "web_search", error="TAVILY_API_KEY is not configured", message="Web search is unavailable")
        try:
            from tavily import TavilyClient
            response = TavilyClient(api_key=TAVILY_API_KEY).search(query=query, max_results=min(max_results, 10), include_answer=True)
            results = [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content"), "source": "Tavily"} for r in response.get("results", [])]
            return ToolResult(True, self.id, "web_search", data={"answer": response.get("answer"), "results": results}, message=f"Found {len(results)} web results")
        except Exception as exc:
            return ToolResult(False, self.id, "web_search", error=str(exc), message="Web search failed")

    def read_url(self, url: str) -> ToolResult:
        try:
            from bs4 import BeautifulSoup
            validate_public_url(url)
            response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 EdithAssistant/1.0"}, allow_redirects=True)
            response.raise_for_status()
            validate_public_url(response.url)
            if len(response.content) > 5_000_000: raise ValueError("Page exceeds the 5 MB limit")
            soup = BeautifulSoup(response.text, "html.parser")
            for node in soup(["script", "style", "noscript", "svg"]): node.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else url
            text = "\n".join(line for line in (part.strip() for part in soup.get_text("\n").splitlines()) if line)
            links = [{"text": a.get_text(" ", strip=True)[:120], "url": a.get("href")} for a in soup.find_all("a", href=True)[:50]]
            return ToolResult(True, self.id, "read_url", data={"title": title, "text": text[:80_000], "links": links, "url": response.url}, message="Webpage read")
        except Exception as exc:
            return ToolResult(False, self.id, "read_url", error=str(exc), message="Webpage reading failed")


class FilesPlugin(Plugin):
    id, name = "files", "Files"
    description = "Read and convert files inside the assistant data directory."
    permissions = ["read and create files in assistant data"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("read_file", "Read a UTF-8 text, CSV, or JSON file from assistant data.", _object({"path": {"type": "string"}}, ["path"]), self.read_file),
            ToolDefinition("create_text_file", "Create an editable plain-text or Markdown notepad artifact.", _object({"filename": {"type": "string"}, "content": {"type": "string"}}, ["content"]), self.create_text_file),
        ]

    def read_file(self, path: str) -> ToolResult:
        try:
            source = approved_path(path)
            if source.stat().st_size > 5_000_000: raise ValueError("File exceeds the 5 MB limit")
            text = source.read_text(encoding="utf-8")
            return ToolResult(True, self.id, "read_file", data={"text": text[:100_000]}, message=f"Read {source.name}")
        except Exception as exc:
            return ToolResult(False, self.id, "read_file", error=str(exc), message="File reading failed")

    def create_text_file(self, content: str, filename: str = "notes.txt") -> ToolResult:
        try:
            extension = "md" if str(filename).lower().endswith(".md") else "txt"
            path = artifact_path(filename, f"notes.{extension}", extension)
            path.write_text(str(content), encoding="utf-8")
            mime_type = "text/markdown" if extension == "md" else "text/plain"
            return ToolResult(True, self.id, "create_text_file", artifacts=[Artifact(path.name, str(path), mime_type)], message="Editable text file created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_text_file", error=str(exc), message="Text file creation failed")


class NotebooksPlugin(Plugin):
    id, name = "notebooks", "Notebooks"
    description = "Create Jupyter/Google Colab-ready IPython notebooks."
    permissions = ["create local notebook artifacts"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_notebook", "Create a valid .ipynb notebook containing Markdown and Python code cells.", _object({
            "filename": {"type": "string"},
            "cells": {"type": "array", "items": {"type": "object", "properties": {
                "type": {"type": "string", "enum": ["markdown", "code"]},
                "content": {"type": "string"},
            }, "required": ["type", "content"]}},
        }, ["cells"]), self.create_notebook)]

    def create_notebook(self, cells: list[dict], filename: str = "notebook.ipynb") -> ToolResult:
        try:
            path = artifact_path(filename, "notebook.ipynb", "ipynb")
            notebook_cells = []
            for item in cells:
                cell_type = "code" if item.get("type") == "code" else "markdown"
                content = str(item.get("content") or "")
                cell = {
                    "cell_type": cell_type,
                    "metadata": {},
                    "source": content.splitlines(keepends=True) or [""],
                }
                if cell_type == "code":
                    cell.update({"execution_count": None, "outputs": []})
                notebook_cells.append(cell)
            payload = {
                "cells": notebook_cells,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return ToolResult(True, self.id, "create_notebook", artifacts=[Artifact(path.name, str(path), "application/x-ipynb+json")], message="IPython notebook created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_notebook", error=str(exc), message="Notebook creation failed")


class VisualizePlugin(Plugin):
    id, name = "visualize", "Visualize"
    description = "Create standalone interactive bar, line, or pie visualizations as HTML artifacts."
    permissions = ["create local interactive visualizations"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_visualization", "Create an interactive HTML chart from labels and numeric values.", _object({
            "title": {"type": "string"}, "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
            "labels": {"type": "array", "items": {"type": "string"}}, "values": {"type": "array", "items": {"type": "number"}}, "filename": {"type": "string"}
        }, ["title", "chart_type", "labels", "values"]), self.create_visualization)]

    def create_visualization(self, title: str, chart_type: str, labels: list[str], values: list[float], filename: str = "visualization.html") -> ToolResult:
        try:
            if not labels or len(labels) != len(values): raise ValueError("labels and values must be non-empty and have the same length")
            path = artifact_path(filename, "visualization.html", "html")
            payload = json.dumps({"type": chart_type, "labels": labels, "values": values}, ensure_ascii=False).replace("</", "<\\/")
            document = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>body{{margin:0;background:#07101f;color:#edf7ff;font:16px system-ui}}main{{max-width:1100px;margin:auto;padding:48px}}h1{{font-size:clamp(32px,5vw,64px)}}#chart{{height:520px;display:flex;align-items:end;gap:18px;border-bottom:1px solid #34445e;padding:30px 10px}}.bar{{flex:1;min-width:28px;background:linear-gradient(#00d9ff,#4355ff);border-radius:12px 12px 0 0;position:relative;transition:.25s}}.bar:hover{{filter:brightness(1.2);transform:translateY(-4px)}}.bar b{{position:absolute;top:-28px;width:100%;text-align:center}}.bar span{{position:absolute;top:calc(100% + 12px);width:100%;text-align:center;color:#9db0ca;font-size:13px}}</style></head><body><main><h1>{html.escape(title)}</h1><div id="chart"></div></main><script>const d={payload},c=document.querySelector('#chart'),m=Math.max(...d.values.map(Math.abs),1);d.labels.forEach((label,i)=>{{const e=document.createElement('div');e.className='bar';e.style.height=(Math.abs(d.values[i])/m*88+2)+'%';e.innerHTML='<b>'+d.values[i]+'</b><span></span>';e.querySelector('span').textContent=label;c.appendChild(e)}})</script></body></html>'''
            path.write_text(document, encoding="utf-8")
            return ToolResult(True, self.id, "create_visualization", artifacts=[Artifact(path.name, str(path), "text/html")], message="Interactive visualization created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_visualization", error=str(exc), message="Visualization creation failed")


class SitesPlugin(Plugin):
    id, name = "sites", "Sites"
    description = "Create polished responsive static websites as downloadable ZIP projects."
    permissions = ["create local website projects"]

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("create_site", "Create a responsive static website project from a title and content sections.", _object({
            "title": {"type": "string"}, "tagline": {"type": "string"}, "filename": {"type": "string"},
            "sections": {"type": "array", "items": {"type": "object", "properties": {"heading": {"type": "string"}, "body": {"type": "string"}}, "required": ["heading", "body"]}}
        }, ["title", "sections"]), self.create_site)]

    def create_site(self, title: str, sections: list[dict], tagline: str = "", filename: str = "site.zip") -> ToolResult:
        try:
            path = artifact_path(filename, "site.zip", "zip")
            blocks = "".join(f'<section><h2>{html.escape(str(item.get("heading", "")))}</h2><p>{html.escape(str(item.get("body", "")))}</p></section>' for item in sections)
            index = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="style.css"><title>{html.escape(title)}</title></head><body><header><nav>E.D.I.T.H. / SITES</nav><h1>{html.escape(title)}</h1><p>{html.escape(tagline)}</p></header><main>{blocks}</main></body></html>'''
            css = ''':root{color-scheme:dark;font-family:Inter,system-ui}*{box-sizing:border-box}body{margin:0;background:#07101f;color:#edf7ff}header{min-height:72vh;padding:8vw;background:radial-gradient(circle at 80% 20%,#173b7a,transparent 45%),#07101f;display:flex;flex-direction:column;justify-content:center}nav{color:#00d9ff;font-weight:800;letter-spacing:.18em}h1{max-width:900px;font-size:clamp(3.4rem,9vw,8rem);line-height:.9;margin:.3em 0}header p{font-size:clamp(1.2rem,2.4vw,2rem);color:#aebcd1;max-width:760px}main{max-width:1100px;margin:auto;padding:6vw 4vw}section{padding:5rem 0;border-top:1px solid #31415d}h2{font-size:clamp(2rem,5vw,4rem);margin:0 0 1rem}section p{font-size:1.2rem;line-height:1.7;color:#bac7da;max-width:760px}@media(max-width:600px){header{padding:28px}main{padding:60px 28px}}'''
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("index.html", index); archive.writestr("style.css", css)
            return ToolResult(True, self.id, "create_site", artifacts=[Artifact(path.name, str(path), "application/zip")], message="Website project created")
        except Exception as exc:
            return ToolResult(False, self.id, "create_site", error=str(exc), message="Website creation failed")


class GitHubPlugin(Plugin):
    id, name = "github", "GitHub"
    description = "Read public GitHub repositories and issues; a GITHUB_TOKEN increases rate limits and enables private access."
    permissions = ["read repository metadata and issues"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("github_repository", "Read GitHub repository metadata.", _object({"owner": {"type": "string"}, "repo": {"type": "string"}}, ["owner", "repo"]), self.repository),
            ToolDefinition("github_issues", "List open GitHub issues.", _object({"owner": {"type": "string"}, "repo": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 30}}, ["owner", "repo"]), self.issues),
        ]

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "EDITH-Assistant"}
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token: headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _repo_url(owner: str, repo: str, suffix: str = "") -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo): raise ValueError("Invalid GitHub owner or repository")
        return f"https://api.github.com/repos/{owner}/{repo}{suffix}"

    def repository(self, owner: str, repo: str) -> ToolResult:
        try:
            response = requests.get(self._repo_url(owner, repo), headers=self._headers(), timeout=15); response.raise_for_status()
            data = response.json(); keep = {key: data.get(key) for key in ("full_name", "description", "html_url", "language", "stargazers_count", "forks_count", "open_issues_count", "default_branch", "updated_at")}
            return ToolResult(True, self.id, "github_repository", data={"repository": keep}, message=f"Read {data.get('full_name')}")
        except Exception as exc:
            return ToolResult(False, self.id, "github_repository", error=str(exc), message="Could not read GitHub repository")

    def issues(self, owner: str, repo: str, max_results: int = 10) -> ToolResult:
        try:
            response = requests.get(self._repo_url(owner, repo, "/issues"), headers=self._headers(), params={"state": "open", "per_page": min(max_results, 30)}, timeout=15); response.raise_for_status()
            issues = [{key: item.get(key) for key in ("number", "title", "html_url", "created_at", "updated_at")} for item in response.json() if "pull_request" not in item]
            return ToolResult(True, self.id, "github_issues", data={"issues": issues}, message=f"Found {len(issues)} open issues")
        except Exception as exc:
            return ToolResult(False, self.id, "github_issues", error=str(exc), message="Could not list GitHub issues")


class PlaceholderPlugin(Plugin):
    def __init__(self, plugin_id: str, name: str, description: str, permissions: list[str] | None = None):
        self.id, self.name, self.description = plugin_id, name, description
        self.permissions = permissions or []
        self.requires_auth = True
        super().__init__()

    @property
    def connected(self) -> bool:
        return False


class GeminiImagePlugin(Plugin):
    id, name = "gemini_image", "Gemini Image"
    description = "Generate Work Mode images directly with Gemini's fast image model."
    permissions = ["send image prompts to the Gemini API", "save generated images locally"]
    requires_auth = True

    @property
    def connected(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(
            "generate_work_image",
            "Generate a new image with Gemini and save it as a local Work Mode artifact.",
            _object({"prompt": {"type": "string"}, "filename_prefix": {"type": "string"}}, ["prompt"]),
            self.generate,
        )]

    def generate(self, prompt: str, filename_prefix: str = "work_image") -> ToolResult:
        try:
            from app.services.gemini_image_service import generate_gemini_image
            path, artifact = generate_gemini_image(prompt, filename_prefix)
            return ToolResult(True, self.id, "generate_work_image", artifacts=[Artifact(artifact["name"], path, artifact["mime_type"])], message="Gemini image generated")
        except Exception as exc:
            return ToolResult(False, self.id, "generate_work_image", error=str(exc), message="Gemini image generation failed")
