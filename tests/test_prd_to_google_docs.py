"""Tests for PRD to Google Docs converter."""

import pytest

from scripts.prd_to_google_docs import MarkdownToDocsConverter, TextSegment


class TestTableParsing:
    """테이블 파싱 및 변환 테스트."""

    def test_parse_simple_table(self):
        """간단한 2x2 테이블 파싱."""
        content = """| Header1 | Header2 |
|---------|---------|
| Cell1   | Cell2   |"""

        converter = MarkdownToDocsConverter(content)
        requests = converter.parse()

        # insertTable 요청이 있어야 함
        table_requests = [r for r in requests if 'insertTable' in r]
        assert len(table_requests) == 1

        table_req = table_requests[0]['insertTable']
        assert table_req['rows'] == 2  # 헤더 + 1 데이터 행
        assert table_req['columns'] == 2

    def test_parse_table_with_3_columns(self):
        """3열 테이블 파싱."""
        content = """| Col1 | Col2 | Col3 |
|------|------|------|
| A    | B    | C    |
| D    | E    | F    |"""

        converter = MarkdownToDocsConverter(content)
        requests = converter.parse()

        table_requests = [r for r in requests if 'insertTable' in r]
        assert len(table_requests) == 1

        table_req = table_requests[0]['insertTable']
        assert table_req['rows'] == 3
        assert table_req['columns'] == 3

    def test_table_cell_data_stored(self):
        """테이블 셀 데이터가 pending_tables에 저장되는지 확인."""
        content = """| Name | Value |
|------|-------|
| foo  | bar   |"""

        converter = MarkdownToDocsConverter(content)
        converter.parse()

        # pending_tables에 테이블 정보 저장 확인
        assert len(converter.pending_tables) == 1
        table = converter.pending_tables[0]
        assert table['num_rows'] == 2
        assert table['num_cols'] == 2
        assert table['rows'][0] == ['Name', 'Value']
        assert table['rows'][1] == ['foo', 'bar']

    def test_table_header_data(self):
        """테이블 헤더 데이터가 올바르게 저장되는지 확인."""
        content = """| Header |
|--------|
| Data   |"""

        converter = MarkdownToDocsConverter(content)
        converter.parse()

        assert len(converter.pending_tables) == 1
        table = converter.pending_tables[0]
        assert table['rows'][0] == ['Header']  # 헤더 행


class TestInlineFormatting:
    """인라인 포맷팅 테스트."""

    def test_parse_bold_text(self):
        """볼드 텍스트 파싱."""
        converter = MarkdownToDocsConverter("")
        result = converter._parse_inline_formatting("This is **bold** text")

        assert len(result.segments) == 3
        assert result.segments[1].bold is True
        assert result.segments[1].text == "bold"

    def test_parse_italic_text(self):
        """이탤릭 텍스트 파싱."""
        converter = MarkdownToDocsConverter("")
        result = converter._parse_inline_formatting("This is *italic* text")

        assert len(result.segments) == 3
        assert result.segments[1].italic is True

    def test_parse_code_text(self):
        """코드 텍스트 파싱."""
        converter = MarkdownToDocsConverter("")
        result = converter._parse_inline_formatting("Use `code` here")

        assert len(result.segments) == 3
        assert result.segments[1].code is True

    def test_parse_link(self):
        """링크 파싱."""
        converter = MarkdownToDocsConverter("")
        result = converter._parse_inline_formatting("Click [here](https://example.com)")

        link_segment = next((s for s in result.segments if s.link), None)
        assert link_segment is not None
        assert link_segment.link == "https://example.com"
        assert link_segment.text == "here"

    def test_parse_strikethrough(self):
        """취소선 파싱."""
        converter = MarkdownToDocsConverter("")
        result = converter._parse_inline_formatting("This is ~~deleted~~ text")

        strike_segment = next((s for s in result.segments if s.strikethrough), None)
        assert strike_segment is not None
        assert strike_segment.text == "deleted"


class TestHeadings:
    """제목 파싱 테스트."""

    def test_heading_levels(self):
        """제목 레벨별 파싱."""
        content = """# H1
## H2
### H3"""

        converter = MarkdownToDocsConverter(content)
        converter.parse()

        assert len(converter.headings) == 3
        assert converter.headings[0]['level'] == 1
        assert converter.headings[1]['level'] == 2
        assert converter.headings[2]['level'] == 3


class TestCodeBlocks:
    """코드 블록 테스트."""

    def test_code_block_with_language(self):
        """언어 지정 코드 블록."""
        content = """```python
def hello():
    pass
```"""

        converter = MarkdownToDocsConverter(content)
        requests = converter.parse()

        # 코드 스타일 (Consolas 폰트) 적용 확인
        font_requests = [
            r for r in requests
            if 'updateTextStyle' in r and
            'weightedFontFamily' in r.get('updateTextStyle', {}).get('textStyle', {})
        ]

        assert len(font_requests) >= 1


class TestChecklist:
    """체크리스트 테스트."""

    def test_unchecked_item(self):
        """미완료 체크리스트 아이템."""
        content = "- [ ] Todo item"

        converter = MarkdownToDocsConverter(content)
        requests = converter.parse()

        # ☐ 문자가 포함된 텍스트 삽입 확인
        text_requests = [r for r in requests if 'insertText' in r]
        texts = [r['insertText']['text'] for r in text_requests]
        assert any('☐' in t for t in texts)

    def test_checked_item(self):
        """완료된 체크리스트 아이템."""
        content = "- [x] Done item"

        converter = MarkdownToDocsConverter(content)
        requests = converter.parse()

        text_requests = [r for r in requests if 'insertText' in r]
        texts = [r['insertText']['text'] for r in text_requests]
        assert any('☑' in t for t in texts)
