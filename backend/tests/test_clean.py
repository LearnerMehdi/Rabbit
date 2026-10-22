from ingest import PageText, clean_text


def one(text: str) -> str:
    return clean_text([PageText(1, text)])[0].text


def test_joins_hyphenated_line_end():
    assert one("the diffu-\nsion equation") == "the diffusion equation"
    assert one("the diffu-  \n  sion equation") == "the diffusion equation"


def test_keeps_hyphen_before_capital():
    assert one("Jean-\nPaul Sartre") == "Jean-Paul Sartre"


def test_keeps_real_hyphens_mid_line():
    assert one("a well-known result") == "a well-known result"


def test_single_breaks_joined_blank_lines_kept():
    text = "first line\nsecond line\n\n\n  \nnext para\nends here"
    assert one(text) == "first line second line\n\nnext para ends here"


def test_normalises_whitespace():
    assert one("  a\t\tb  c   d \r\ne­f ") == "a b c d ef"


def test_keeps_page_numbers_and_empty_pages():
    pages = clean_text([PageText(1, "x"), PageText(2, " \n "), PageText(3, "y")])
    assert [p.page for p in pages] == [1, 2, 3]
    assert pages[1].text == ""
    assert pages.empty_pages == 1
    assert not pages.needs_ocr


def test_needs_ocr_threshold():
    def pages(n_text, n_empty):
        return [PageText(i + 1, "text" if i < n_text else "") for i in range(n_text + n_empty)]

    assert clean_text(pages(1, 9)).needs_ocr  # 90% empty
    assert not clean_text(pages(2, 8)).needs_ocr  # exactly 80% is not "more than"
    assert clean_text([]).needs_ocr
