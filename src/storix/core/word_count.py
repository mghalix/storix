from collections.abc import Callable, Iterator, Mapping, Sized
from typing import (
    Literal,
    Self,
    TypedDict,
    Unpack,
    cast,
    final,
    overload,
)


class DefaultWordCountResult(TypedDict, total=True):
    words: int
    lines: int
    chars: int


Counts = Literal["words", "lines", "chars"]


class WordCountResult(Mapping[Counts, int]):
    __slots__ = ("_counts",)

    def __init__(self, **counts: Unpack[DefaultWordCountResult]) -> None:
        self._counts = cast(Mapping[Counts, int], counts)

    @property
    def words(self) -> int:
        return self._counts["words"]

    @property
    def chars(self) -> int:
        return self._counts["chars"]

    @property
    def lines(self) -> int:
        return self._counts["lines"]

    def __repr__(self) -> str:
        return f"\t{self.words}\t{self.lines}\t{self.chars}"

    # mapping interface
    def __getitem__(self, key: Counts, /) -> int:
        return self._counts[key]

    def __iter__(self) -> Iterator[Counts]:
        return iter(self._counts)

    def __len__(self) -> int:
        return len(self._counts)


# Countable = Findable
Countable = Sized


class WordCountArg:
    __slots__ = ("_counter",)

    def __init__(self, counter: Callable[[Countable], int]) -> None:
        self._counter = counter

    def __ror__(self, value: Countable, /) -> int:
        if not isinstance(value, Countable):
            return NotImplemented
        return self._counter(value)


@final
class WordCount:
    """Word count."""

    __slots__ = ()

    @overload
    def with_counts(self, *, w: Literal[True]) -> WordCountArg: ...
    @overload
    def with_counts(self, *, l: Literal[True]) -> WordCountArg: ...  # noqa: E741
    @overload
    def with_counts(self, *, m: Literal[True]) -> WordCountArg: ...

    def with_counts(
        self,
        *,
        w: bool = False,
        l: bool = False,  # noqa: E741
        m: bool = False,
    ) -> Self | WordCountArg:
        counts: Mapping[Counts, bool] = {
            "words": w,
            "lines": l,
            "chars": m,
        }

        if not any(counts.values()):
            return self

        if sum(counts.values()) > 1:
            raise ValueError(
                "Only one of the counts must only be set when using `with_counts`. "
                f"Got: {counts}"
            )

        key: Counts = next(k for k, v in counts.items() if v)
        mapping: Mapping[Counts, Callable[[Countable], int]] = {
            "words": self._count_words,
            "lines": self._count_lines,
            "chars": self._count_chars,
        }

        return WordCountArg(mapping[key])

    def _counts(self, value: Countable) -> DefaultWordCountResult:
        return DefaultWordCountResult(
            words=self._count_words(value),
            lines=self._count_lines(value),
            chars=self._count_chars(value),
        )

    def _count_words(self, value: Countable) -> int:
        return len(str(value).split())

    def _count_chars(self, value: Countable) -> int:
        return len(str(value))

    def _count_lines(self, value: Countable) -> int:
        return len(value)

    def __ror__(self, value: Countable, /) -> WordCountResult:
        if not isinstance(value, Countable):
            return NotImplemented

        return WordCountResult(**self._counts(value))


wc = WordCount()
