# /// script
# dependencies = [
#     "drissionpage>=4.1.0.18",
#     "loguru>=0.7.3",
#     "typer>=0.15.2",
#     "yarl>=1.18.3",
# ]
# ///
from typing import Annotated
from DrissionPage import ChromiumOptions, ChromiumPage
from loguru import logger
from yarl import URL
import atexit
import typer


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
    num: Annotated[
        int,
        typer.Option(
            help="Max number of results, -1 for unlimited",
        ),
    ] = -1,
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

    count = 0

    while True:
        eles = tab.eles("css:h3 > a:not([href])")
        for ele in eles.__iter__():
            ele.hover()

            imgres = ele.attr("href")
            if imgres is None:
                logger.warning("imgres is None after hover")
                continue

            url = URL(imgres).query.get("imgurl")
            if not url:
                logger.warning(imgres)
                continue

            title = ele.parent(2).next()
            if isinstance(title, str):
                logger.warning(title)
                continue

            link = title.ele("css:a")
            text = link.text
            source = link.attr("href")
            logger.info(
                {
                    "url": url,
                    "text": text,
                    "source": source,
                }
            )
            count += 1
            if num > 0 and count >= num:
                break


if __name__ == "__main__":
    typer.run(main)
