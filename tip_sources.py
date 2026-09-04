from typing import List, Dict


TIP_SOURCES: List[Dict] = [

    # -------------------------------------------------
    # AKTIETIPS / ANALYSER
    # -------------------------------------------------

    {
        "name": "Metro Finans",
        "url": "https://www.metrofinans.se/",
        "type": "aktietips",
        "priority": 8,
    },

    {
        "name": "TradeVenue Aktietips",
        "url": "https://tradevenue.se/aktietips",
        "type": "aktietips",
        "priority": 8,
    },

    {
        "name": "Nordnet Analys",
        "url": "https://www.nordnet.se/blogg/kategori/analys",
        "type": "aktietips",
        "priority": 7,
    },

    {
        "name": "Placera",
        "url": "https://www.placera.se/",
        "type": "aktietips",
        "priority": 7,
    },

    {
        "name": "Aktiebloggen",
        "url": "https://aktiebloggen.nu/",
        "type": "aktietips",
        "priority": 6,
    },

    # -------------------------------------------------
    # NYHETER / MARKNAD
    # -------------------------------------------------

    {
        "name": "Aktieforumet",
        "url": "https://www.aktieforumet.se/",
        "type": "nyheter",
        "priority": 7,
    },

    {
        "name": "InvesteraMera",
        "url": "https://www.investeramera.se/",
        "type": "nyheter",
        "priority": 6,
    },

    # -------------------------------------------------
    # NYEMISSIONER / IPO
    # -------------------------------------------------

    {
        "name": "Aktieforumet Nyemissioner",
        "url": "https://www.aktieforumet.se/nyemissioner",
        "type": "nyemission",
        "priority": 9,
    },

    {
        "name": "TradeVenue Nyemissioner",
        "url": "https://tradevenue.se/",
        "type": "nyemission",
        "priority": 7,
    },

    # -------------------------------------------------
    # KÄLLOR SOM AI:N SKA KUNNA JÄMFÖRA MED
    # -------------------------------------------------

    {
        "name": "MFN",
        "url": "https://mfn.se/",
        "type": "pressmeddelanden",
        "priority": 8,
    },

    {
        "name": "Finansinspektionen",
        "url": "https://www.fi.se/",
        "type": "myndighetsdata",
        "priority": 10,
    },
]


def get_sources() -> List[Dict]:
    return TIP_SOURCES


def get_sources_by_type(source_type: str) -> List[Dict]:
    return [
        source
        for source in TIP_SOURCES
        if source["type"] == source_type
    ]


if __name__ == "__main__":
    for source in TIP_SOURCES:
        print(
            f'{source["priority"]} | '
            f'{source["type"]:<18} | '
            f'{source["name"]} | '
            f'{source["url"]}'
        )
