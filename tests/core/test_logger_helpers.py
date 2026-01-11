from sec_nlp.core.infra.logger import center_block, visible_length


def test_visible_length_strips_ansi_codes() -> None:
    text = "\x1b[31mfoo\x1b[0m"
    assert visible_length(text) == 3


def test_center_block_maintains_padding() -> None:
    block = "A\nBB"
    centered = center_block(block, width=10)
    lines = centered.strip("\n").splitlines()

    assert len(lines) == 2
    leading_spaces = [len(line) - len(line.lstrip(" ")) for line in lines]
    assert leading_spaces[0] == leading_spaces[1]
    assert leading_spaces[0] > 0
    assert all(len(line) <= 10 for line in lines)
