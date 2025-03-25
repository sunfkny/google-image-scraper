# /// script
# dependencies = [
#     "drissionpage>=4.1.0.18",
#     "loguru>=0.7.3",
#     "requests>=2.32.3",
#     "typer>=0.15.2",
#     "yarl>=1.18.3",
# ]
# ///
import atexit
import itertools
import json
import pathlib
import time
from typing import Annotated, Any, NamedTuple, Sequence, TypedDict, cast
from loguru import logger
import requests
import typer
from yarl import URL
from DrissionPage import ChromiumOptions, ChromiumPage
from DrissionPage._units.listener import DataPacket
from DrissionPage._pages.mix_tab import MixTab

PREFIX = ")]}'\n"


def parse_search(body: str):
    body = body.removeprefix(PREFIX)
    while body:
        seg_len_str_index = body.index(";")
        seg_len = int(body[:seg_len_str_index], 16)
        yield body[seg_len_str_index + 1 : seg_len_str_index + 1 + seg_len]
        body = body[seg_len_str_index + 1 + seg_len :]


def from_iterable(cls, s: Sequence):
    s = s[: len(cls.__annotations__)]
    return cls(*s)


class ResultEncrypted(NamedTuple):
    field0_url: str
    field1_height: int
    field2_width: int


class ResultImage(NamedTuple):
    field0_url: str
    field1_height: int
    field2_width: int


class ResultMetadata2003(NamedTuple):
    field0: Any
    field1: Any
    field2_source: str
    field3_title: str


ResultMetadata = TypedDict(
    "ResultMetadata",
    {
        "2000": Any,
        "2001": Any,
        "2003": ResultMetadata2003,
        "2008": Any,
    },
)


class Result3(NamedTuple):
    field0: Any
    field1: Any
    field2_encrypted: ResultEncrypted
    field3_image: ResultImage
    field4: Any
    field5: Any
    field6: Any
    field7: Any
    field8: Any
    field9_metadata: ResultMetadata


class Result2(NamedTuple):
    field0: Any
    field1_result3: Result3
    field2: Any
    field3: Any
    field4: Any
    field5: Any
    field6: Any
    field7: Any


class Result1(NamedTuple):
    field0: Any
    field1_result2: Result2


class Result0(NamedTuple):
    field0: Any
    field1: Any
    field2: Any
    field3: Any
    field4: Any
    field5: Any = None
    field6_result1_str: str | None = None


def get_image_data(d):
    result1 = from_iterable(Result1, d)
    result2 = from_iterable(Result2, result1.field1_result2)
    result3 = from_iterable(Result3, result2.field1_result3)
    image = from_iterable(ResultImage, result3.field3_image)

    metadata = result3.field9_metadata
    metadata2003 = from_iterable(ResultMetadata2003, metadata["2003"])
    return {
        "url": image.field0_url,
        "height": image.field1_height,
        "width": image.field2_width,
        "source": metadata2003.field2_source,
        "title": metadata2003.field3_title,
    }


def main(
    q: Annotated[
        str,
        typer.Argument(
            help="Search query",
        ),
    ],
    headless: Annotated[
        bool,
        typer.Option(
            help="Run in headless mode",
        ),
    ] = False,
    write_debug_files: Annotated[
        bool,
        typer.Option(
            help="Write debug files",
        ),
    ] = False,
):
    co = ChromiumOptions()
    co.incognito()
    co.set_pref("intl.accept_languages", "en-US")
    co.set_argument("--accept-lang=en-US")
    co.headless(headless)

    driver = ChromiumPage(addr_or_opts=co)
    if headless:
        atexit.register(driver.quit)

    driver = ChromiumPage(addr_or_opts=co)
    tab = driver.latest_tab
    assert not isinstance(tab, str)
    tab = cast(MixTab, tab)
    url = URL("https://www.google.com/search") % {"q": q, "udm": 2}
    tab.get(str(url))
    tab.listen.start("https://www.google.com/search")
    for _ in range(3):
        tab.scroll.to_bottom()
        time.sleep(0.5)
    packet = tab.listen.wait(count=1)
    assert isinstance(packet, DataPacket)
    api_url = packet.url
    logger.info(f"Api url: {api_url}")
    tab.listen.stop()
    driver.close()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": packet.request.headers["User-Agent"],
            "Cookie": packet.request.headers["Cookie"],
        }
    )

    debug_files_dir = pathlib.Path(f"./output_debug/{q}/")
    if write_debug_files:
        debug_files_dir.mkdir(exist_ok=True, parents=True)
    output_dir = pathlib.Path("./output/")
    output_dir.mkdir(exist_ok=True)

    start = 0
    all_datas = []
    while True:
        url = str(URL(api_url) % {"start": start})
        logger.info(f"Requesting {start=}")
        response = session.get(url)
        response.raise_for_status()

        if write_debug_files:
            (debug_files_dir / f"{start:04d}-response.txt").write_bytes(
                response.content
            )

        parsed = list(parse_search(response.text))
        if write_debug_files:
            (debug_files_dir / f"{start:04d}-parsed0.json").write_text(
                json.dumps(parsed, indent=4, ensure_ascii=False)
            )

        result0 = from_iterable(Result0, parsed)

        if not result0.field6_result1_str:
            logger.info("No more results")
            break

        datas = [
            [k, json.loads(v)]
            for k, v in itertools.chain.from_iterable(
                i[2:-1] for i in json.loads(result0.field6_result1_str)
            )
        ]

        if write_debug_files:
            (debug_files_dir / f"{start:04d}-parsed1.json").write_text(
                json.dumps(datas, indent=4, ensure_ascii=False)
            )

        datas = [get_image_data(i) for i in datas]
        if write_debug_files:
            (debug_files_dir / f"{start:04d}-parsed2.json").write_text(
                json.dumps(datas, indent=4, ensure_ascii=False)
            )

        all_datas.extend(datas)
        logger.info(f"Get: {len(datas)}")
        start += 10

    logger.info(f"Total: {len(all_datas)}")
    (output_dir / f"{q}.json").write_text(
        json.dumps(all_datas, indent=4, ensure_ascii=False)
    )


if __name__ == "__main__":
    typer.run(main)
