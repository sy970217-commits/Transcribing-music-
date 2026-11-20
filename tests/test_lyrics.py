import pytest
from music21 import note, stream

from transcriber.lyrics import HOLD, LyricsError, attach_lyrics, parse_lyrics, read_lyrics_file


def test_each_hangul_letter_is_one_syllable():
    assert parse_lyrics("달빛 아래\n노래") == ("달", "빛", "아", "래", "노", "래")


def test_dash_means_hold_previous_letter():
    assert parse_lyrics("하나- 둘") == ("하", "나", HOLD, "둘")
    assert parse_lyrics("하 - - 나") == ("하", HOLD, HOLD, "나")


def test_extension_marks_take_no_note():
    # "ㅡ"는 앞 음의 연장 표시라 음표를 차지하지 않는다
    assert parse_lyrics("흔 들 ㅡ 리") == ("흔", "들", "리")
    assert parse_lyrics("는— 순") == ("는", "순")


def test_punctuation_is_ignored():
    assert parse_lyrics("안녕, 하세요!") == ("안", "녕", "하", "세", "요")


def test_latin_words_stay_whole():
    assert parse_lyrics("Hello 별 world") == ("Hello", "별", "world")


def make_melody(count):
    part = stream.Part()
    for i in range(count):
        part.insert(i, note.Note(60 + i, quarterLength=1))
    return part


def lyrics_on(part):
    return [n.lyric for n in part.recurse().notes]


def test_attaches_syllables_in_order_and_skips_holds():
    part = make_melody(4)

    used = attach_lyrics(part, ("가", HOLD, "나", "다"))

    assert used == 4
    assert lyrics_on(part) == ["가", None, "나", "다"]


def test_extra_syllables_are_left_over():
    part = make_melody(2)

    used = attach_lyrics(part, ("가", "나", "다"))

    assert used == 2
    assert lyrics_on(part) == ["가", "나"]


def test_reads_lyrics_file(tmp_path):
    lyrics_file = tmp_path / "가사.txt"
    lyrics_file.write_text("가을 꽃-", encoding="utf-8")

    assert read_lyrics_file(lyrics_file) == ("가", "을", "꽃", HOLD)


def test_missing_lyrics_file_raises_clear_error(tmp_path):
    with pytest.raises(LyricsError, match="찾을 수 없습니다"):
        read_lyrics_file(tmp_path / "없음.txt")


def test_empty_lyrics_file_raises_clear_error(tmp_path):
    empty = tmp_path / "빈.txt"
    empty.write_text("  ...  ", encoding="utf-8")

    with pytest.raises(LyricsError, match="글자가 없습니다"):
        read_lyrics_file(empty)
