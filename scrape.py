#!/usr/bin/env python

import argparse
import asyncio
import functools
import re
from dataclasses import dataclass

import aiohttp
import bs4
import pandas as pd
from tqdm import tqdm

# Track total number of requests because all conferences are scraped in parallel
REQUESTS_PBAR: tqdm = None

# Restrict number of concurrent requests. If we would open all thousands of requests at
# once, some would inevitably time out at some point.
OPEN_REQUESTS: asyncio.Semaphore = None


def retry_on_server_disconnect(n_tries: int):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            for i in range(n_tries):
                try:
                    return await f(*args, **kwargs)
                except aiohttp.client_exceptions.ClientConnectionError as e:
                    if i == n_tries - 1:
                        print("Client error, try again: {e}")
                        raise

        return wrapper

    return decorator


@retry_on_server_disconnect(3)
async def load_doc_from_url(session: aiohttp.ClientSession, url: str):
    REQUESTS_PBAR.total += 1
    async with OPEN_REQUESTS:
        async with session.get(url) as response:
            doc = bs4.BeautifulSoup(await response.text(), features="lxml")
            REQUESTS_PBAR.update()
            return doc


async def load_paper_ids(session: aiohttp.ClientSession, url):
    doc = await load_doc_from_url(session, url)
    cards = doc.select(".maincard.Poster")

    return [c.attrs["id"][9:] for c in cards]


async def load_paper(session: aiohttp.ClientSession, url):
    doc = await load_doc_from_url(session, url)
    box = doc.select(".maincard")[0].parent
    title = box.select(".maincardBody")[0].text.strip()
    authors = [
        (b.text.strip()[:-2].strip(), b.attrs["onclick"][13:-3])
        for b in box.findAll("button")
    ]

    return title, authors


async def load_author(session: aiohttp.ClientSession, url):
    doc = await load_doc_from_url(session, url)
    box = doc.select(".maincard")[0].parent
    name = box.find("h3").text.strip()
    affiliation = box.find("h4").text.strip()

    return name, affiliation


@dataclass
class Conference:
    name: str
    host: str
    first_year: int

    def papers_url(self, year: int):
        return f"https://{self.host}/Conferences/{year:d}/Schedule"

    def paper_url(self, year: int, id: str):
        return f"https://{self.host}/Conferences/{year:d}/Schedule?showEvent={id}"

    def author_url(self, year: int, id: str):
        return f"https://{self.host}/Conferences/{year:d}/Schedule?showSpeaker={id}"

    async def scrape(self, year: int, session: aiohttp.ClientSession):
        paper_ids = await load_paper_ids(session, self.papers_url(year))
        paper_links = [self.paper_url(year, id) for id in paper_ids]
        paper_tasks = [load_paper(session, link) for link in paper_links]
        paper_data = await asyncio.gather(*paper_tasks)

        author_ids = list(
            set([id for _, authors in paper_data for name, id in authors])
        )
        author_links = [self.author_url(year, id) for id in author_ids]
        author_tasks = [load_author(session, link) for link in author_links]
        author_data = await asyncio.gather(*author_tasks)
        affiliations = dict(author_data)

        papers = [
            (title, [(name, affiliations[name]) for name, _ in authors])
            for title, authors in paper_data
        ]

        unnormalized = [
            (title, author, affiliation)
            for title, authors in papers
            for author, affiliation in authors
        ]

        papers = pd.DataFrame(unnormalized, columns=["Title", "Author", "Affiliation"])
        papers.insert(0, "Conference", self.name)
        papers.insert(1, "Year", year)
        return papers


CONFERENCES = [
    Conference("ICML", "icml.cc", 2017),
    Conference("NeurIPS", "neurips.cc", 2006),
    Conference("ICLR", "iclr.cc", 2018),
]


async def main():
    global REQUESTS_PBAR, OPEN_REQUESTS

    parser = argparse.ArgumentParser(
        description="Scrape paper data from ICML, NeurIPS and ICLR."
    )
    parser.add_argument(
        "-o",
        "--output",
        default="papers.csv",
        help="Where to store the data [Default: papers.csv]",
    )
    parser.add_argument(
        "--parallel",
        default=500,
        type=int,
        help="Number of parallel requests [Default: 500]",
    )
    parser.add_argument("years", help="Year or year range")
    args = parser.parse_args()

    output = args.output
    parallel = args.parallel
    years = args.years

    OPEN_REQUESTS = asyncio.Semaphore(parallel)

    if "-" in years:
        match = re.match(r"^(\d+)-(\d+)$", years)
        assert match, f"Invalid year range {years}; expected e.g. 2008-2010"
        start, end = int(match[1]), int(match[2])
    else:
        start = end = int(years)
    year_range = range(start, end + 1)

    conferences = CONFERENCES

    cf_names = ", ".join(c.name for c in conferences)
    print(f"Scraping papers from {start}-{end} in {cf_names} into {output}")

    with tqdm(total=0) as pbar:
        REQUESTS_PBAR = pbar
        async with aiohttp.ClientSession() as session:
            paper_tasks = [
                conf.scrape(year, session)
                for conf in conferences
                for year in year_range
                if year >= conf.first_year
            ]
            papers = await asyncio.gather(*paper_tasks)

    df = pd.concat(papers)
    # Sort rows by [Year, Conference] while keeping the authors in the original order
    df = df.sort_values(by="Conference", kind="mergesort")
    df = df.sort_values(by="Year", kind="mergesort")

    # Fix multiple spaces in author names
    df["Author"] = df["Author"].replace("\s+", " ", regex=True)

    df.to_csv(output, index=False)


if __name__ == "__main__":
    asyncio.run(main())
