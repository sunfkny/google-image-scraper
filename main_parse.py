# /// script
# dependencies = [
#     "drissionpage>=4.1.0.18",
#     "loguru>=0.7.3",
#     "requests>=2.32.3",
#     "typer>=0.15.2",
#     "yarl>=1.18.3",
# ]
# ///
import array
import atexit
import itertools
import json
import pathlib
import time
from typing import Annotated
from loguru import logger
import requests
import typer
from yarl import URL
from DrissionPage import ChromiumOptions, ChromiumPage
from DrissionPage._units.listener import DataPacket

PREFIX = ")]}'\n"


def parse_search(body: str):
    body = body.removeprefix(PREFIX)
    utf16_units = array.array("H", body.encode("utf-16-le"))
    index = 0
    while index < len(utf16_units):
        if ord(";") in utf16_units[index:]:
            seg_len_str_index = index + utf16_units[index:].index(ord(";"))
        else:
            break

        seg_len = int("".join(map(chr, utf16_units[index:seg_len_str_index])), 16)

        start = seg_len_str_index + 1
        end = start + seg_len
        segment = utf16_units[start:end]

        yield segment.tobytes().decode("utf-16-le")

        index = end


def get_image_data(d):
    try:
        _, result2, *_ = d
        if not result2 or len(result2) < 2:
            return None
        _, result3, *_ = result2
        if not result3:
            return None
        _, _, _, image, *_, metadata = result3
        url, height, width, *_ = image
        _, _, source, title, *_ = metadata["2003"]

        return {
            "url": url,
            "height": height,
            "width": width,
            "source": source,
            "title": title,
        }
    except Exception:
        logger.error(f"Failed to parse data: {d}")
        return None


def get_datas_from_parsed(parsed: list[str]):
    datas_str_index = 6
    if len(parsed) < datas_str_index + 1:
        logger.info("No more results")
        return None

    datas_str = parsed[datas_str_index]

    datas = [
        [k, json.loads(v)]
        for k, v in itertools.chain.from_iterable(json.loads(datas_str))
    ]
    return datas


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
    tab = driver.latest_tab
    assert not isinstance(tab, str)
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

        datas = get_datas_from_parsed(parsed)
        if datas is None:
            break

        if write_debug_files:
            (debug_files_dir / f"{start:04d}-parsed1.json").write_text(
                json.dumps(datas, indent=4, ensure_ascii=False)
            )

        datas = [get_image_data(i) for i in datas]
        datas = [i for i in datas if i is not None]
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
