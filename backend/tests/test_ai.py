from glyph.ai import MockAiAdapter, classify_block, normalize_source_text


def test_classifies_formula_figure_and_table_blocks():
    assert classify_block("E[R] = rf + beta * (rm - rf)") == "formula"
    assert classify_block("Figure 2.2 Chess board with alternative squares") == "figure"
    assert classify_block("Table 4.1 Summary statistics") == "table"


def test_formula_normalization_preserves_line_breaks_and_spacing():
    source = "E[R] = rf + beta * (rm - rf)\nVar(aX + bY) = a^2 Var(X) + b^2 Var(Y)"

    assert normalize_source_text(source, "formula") == source


def test_mock_ai_keeps_formula_as_readable_block():
    parsed = MockAiAdapter().parse_translate_and_summarize(
        [
            (
                3,
                "# CAPM\n\nE[R] = rf + beta * (rm - rf)\nVar(R) = sigma^2\n\nFigure 1.1 Payoff diagram",
            )
        ]
    )

    assert [block.block_type for block in parsed.blocks] == [
        "heading",
        "formula",
        "figure",
    ]
    assert parsed.blocks[1].page_number == 3
    assert "\n" in parsed.blocks[1].source_text


def test_table_of_contents_block_is_not_promoted_to_giant_heading():
    toc = (
        "Chapter 2 Brain Teasers ................................................................................................. 3\n"
        "2.1 Problem Simplification ............................................................................................ 3\n"
        "Screwy pirates ................................................................................................................. 3"
    )

    assert classify_block(toc) == "paragraph"


def test_mock_ai_extracts_heading_from_page_number_prefixed_block():
    parsed = MockAiAdapter().parse_translate_and_summarize(
        [
            (
                4,
                "2\n"
                "Chapter 2 Brain Teasers\n"
                "In this chapter, we cover problems that only require common sense.",
            )
        ]
    )

    assert [block.block_type for block in parsed.blocks] == ["heading", "paragraph"]
    assert parsed.blocks[0].source_text == "Chapter 2 Brain Teasers"
    assert parsed.blocks[1].source_text.startswith("In this chapter")
    assert parsed.sections[0].title == "Chapter 2 Brain Teasers"
