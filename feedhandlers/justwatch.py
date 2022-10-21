import requests
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_url_title_details(url, headers):
    split_url = urlsplit(url)
    query = {
        "operationName": "GetUrlTitleDetails",
        "variables":{
            "platform": "WEB",
            "fullPath": split_url.path,
            "language": "en",
            "country": "US",
            "episodeMaxLimit": 20
        },
        "query": "query GetUrlTitleDetails($fullPath: String!, $country: Country!, $language: Language!, $episodeMaxLimit: Int, $platform: Platform! = WEB) {\n  url(fullPath: $fullPath) {\n    id\n    metaDescription\n    metaKeywords\n    metaRobots\n    metaTitle\n    heading1\n    heading2\n    htmlContent\n    node {\n      id\n      ... on MovieOrShowOrSeason {\n        objectType\n        objectId\n        offerCount(country: $country, platform: $platform)\n        offers(country: $country, platform: $platform) {\n          monetizationType\n          package {\n            packageId\n            __typename\n          }\n          __typename\n        }\n        promotedBundles(country: $country, platform: $platform) {\n          promotionUrl\n          __typename\n        }\n        availableTo(country: $country, platform: $platform) {\n          availableToDate\n          package {\n            shortName\n            __typename\n          }\n          __typename\n        }\n        content(country: $country, language: $language) {\n          backdrops {\n            backdropUrl\n            __typename\n          }\n          clips {\n            externalId\n            __typename\n          }\n          externalIds {\n            imdbId\n            __typename\n          }\n          fullPath\n          genres {\n            shortName\n            __typename\n          }\n          posterUrl\n          runtime\n          scoring {\n            imdbScore\n            imdbVotes\n            tmdbPopularity\n            tmdbScore\n            __typename\n          }\n          shortDescription\n          title\n          originalReleaseYear\n          upcomingReleases(releaseTypes: DIGITAL) {\n            releaseDate\n            label\n            package {\n              packageId\n              shortName\n              __typename\n            }\n            __typename\n          }\n          ... on MovieOrShowContent {\n            ageCertification\n            credits {\n              role\n              name\n              characterName\n              personId\n              __typename\n            }\n            productionCountries\n            __typename\n          }\n          ... on SeasonContent {\n            seasonNumber\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on MovieOrShow {\n        watchlistEntry {\n          createdAt\n          __typename\n        }\n        likelistEntry {\n          createdAt\n          __typename\n        }\n        dislikelistEntry {\n          createdAt\n          __typename\n        }\n        __typename\n      }\n      ... on Movie {\n        seenlistEntry {\n          createdAt\n          __typename\n        }\n        __typename\n      }\n      ... on Show {\n        totalSeasonCount\n        seenState(country: $country) {\n          progress\n          seenEpisodeCount\n          __typename\n        }\n        seasons(sortDirection: DESC) {\n          id\n          objectId\n          objectType\n          availableTo(country: $country, platform: $platform) {\n            availableToDate\n            package {\n              shortName\n              __typename\n            }\n            __typename\n          }\n          content(country: $country, language: $language) {\n            posterUrl\n            seasonNumber\n            fullPath\n            upcomingReleases(releaseTypes: DIGITAL) {\n              releaseDate\n              package {\n                shortName\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          show {\n            id\n            objectId\n            objectType\n            watchlistEntry {\n              createdAt\n              __typename\n            }\n            content(country: $country, language: $language) {\n              title\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        recentEpisodes: episodes(\n          sortDirection: DESC\n          limit: 3\n          releasedInCountry: $country\n        ) {\n          id\n          objectId\n          content(country: $country, language: $language) {\n            title\n            shortDescription\n            episodeNumber\n            seasonNumber\n            upcomingReleases {\n              releaseDate\n              label\n              __typename\n            }\n            __typename\n          }\n          seenlistEntry {\n            createdAt\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Season {\n        totalEpisodeCount\n        episodes(limit: $episodeMaxLimit) {\n          id\n          objectType\n          objectId\n          seenlistEntry {\n            createdAt\n            __typename\n          }\n          content(country: $country, language: $language) {\n            title\n            shortDescription\n            episodeNumber\n            seasonNumber\n            upcomingReleases(releaseTypes: DIGITAL) {\n              releaseDate\n              label\n              package {\n                packageId\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        show {\n          id\n          objectId\n          objectType\n          totalSeasonCount\n          content(country: $country, language: $language) {\n            title\n            ageCertification\n            fullPath\n            credits {\n              role\n              name\n              characterName\n              personId\n              __typename\n            }\n            productionCountries\n            externalIds {\n              imdbId\n              __typename\n            }\n            upcomingReleases(releaseTypes: DIGITAL) {\n              releaseDate\n              __typename\n            }\n            backdrops {\n              backdropUrl\n              __typename\n            }\n            posterUrl\n            __typename\n          }\n          seenState(country: $country) {\n            progress\n            __typename\n          }\n          watchlistEntry {\n            createdAt\n            __typename\n          }\n          dislikelistEntry {\n            createdAt\n            __typename\n          }\n          likelistEntry {\n            createdAt\n            __typename\n          }\n          __typename\n        }\n        seenState(country: $country) {\n          progress\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    }
    return utils.post_url('https://apis.justwatch.com/graphql', json_data=query, headers=headers)


def get_title_offers(node_id, headers):
    query = {
        "operationName": "GetTitleOffers",
        "variables": {
            "platform": "WEB",
            "nodeId": node_id,
            "country": "US",
            "language": "en",
            "filterBuy": {
                "monetizationTypes": ["BUY"],
                "bestOnly": True
            },
            "filterFlatrate": {
                "monetizationTypes": ["FLATRATE","FLATRATE_AND_BUY","ADS","FREE"],
                "bestOnly":True
            },
            "filterRent": {
                "monetizationTypes": ["RENT"],
                "bestOnly": True
            },
            "filterFree": {
                "monetizationTypes": ["ADS","FREE"],
                "bestOnly": True
            }
        },
        "query": "query GetTitleOffers($nodeId: ID!, $country: Country!, $language: Language!, $filterFlatrate: OfferFilter!, $filterBuy: OfferFilter!, $filterRent: OfferFilter!, $filterFree: OfferFilter!, $platform: Platform! = WEB) {\n  node(id: $nodeId) {\n    ... on MovieOrShowOrSeasonOrEpisode {\n      offerCount(country: $country, platform: $platform)\n      flatrate: offers(\n        country: $country\n        platform: $platform\n        filter: $filterFlatrate\n      ) {\n        ...TitleOffer\n        __typename\n      }\n      buy: offers(country: $country, platform: $platform, filter: $filterBuy) {\n        ...TitleOffer\n        __typename\n      }\n      rent: offers(country: $country, platform: $platform, filter: $filterRent) {\n        ...TitleOffer\n        __typename\n      }\n      free: offers(country: $country, platform: $platform, filter: $filterFree) {\n        ...TitleOffer\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment TitleOffer on Offer {\n  id\n  presentationType\n  monetizationType\n  retailPrice(language: $language)\n  retailPriceValue\n  currency\n  lastChangeRetailPriceValue\n  type\n  package {\n    packageId\n    clearName\n    __typename\n  }\n  standardWebURL\n  elementCount\n  availableTo\n  deeplinkRoku: deeplinkURL(platform: ROKU_OS)\n  __typename\n}\n"
    }
    return utils.post_url('https://apis.justwatch.com/graphql', json_data=query, headers=headers)


def get_content(url, args, save_debug=False):
    session = requests.Session()
    r = session.get('https://www.justwatch.com/us')
    cookies = session.cookies.get_dict()
    if not cookies.get('jw_id'):
        logger.warning('unable to determine jw_id')
        return None
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "device-id": cookies['jw_id'],
        "sec-ch-ua": "\"Chromium\";v=\"106\", \"Microsoft Edge\";v=\"106\", \"Not;A=Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42"
    }
    title_details = get_url_title_details(url, headers)
    if not title_details:
        return None
    if save_debug:
        utils.write_file(title_details, './debug/debug.json')

    item = {}
    item['id'] = title_details['data']['url']['node']['id']
    item['url'] = 'https://www.justwatch.com' + title_details['data']['url']['node']['content']['fullPath']
    item['title'] = title_details['data']['url']['node']['content']['title']

    item['tags'] = title_details['data']['url']['metaKeywords'].split(', ')
    item['_image'] = 'https://images.justwatch.com' + title_details['data']['url']['node']['content']['posterUrl'].replace('{profile}', 's592').replace('{format}', 'webp')
    item['summary'] = title_details['data']['url']['node']['content']['shortDescription']

    item['content_html'] = '<table style="width:90%; margin-right:auto; margin-left:auto;"><tr><td style="width:128px; vertical-align:top;"><a href="{}"><img src="{}" style="width:128px"/></a></td><td style="vertical-align:top;"><a href="{}"><span style="font-size:1.1em; font-weight:bold;">{} ({})</b></a><br/><small>{}</small>'.format(item['url'], item['_image'], item['url'], item['title'], title_details['data']['url']['node']['content']['originalReleaseYear'], item['summary'])

    if title_details['data']['url']['node']['content'].get('ageCertification'):
        item['content_html'] += '<br/><small>Rated: {}</small>'.format(title_details['data']['url']['node']['content']['ageCertification'])
    if title_details['data']['url']['node']['content']['scoring'].get('imdbScore'):
        item['content_html'] += '<br/><small>IMDB score: {}</small>'.format(title_details['data']['url']['node']['content']['scoring']['imdbScore'])
    if title_details['data']['url']['node']['content'].get('runtime'):
        item['content_html'] += '<br/><small>Runtime: {} min.</small>'.format(title_details['data']['url']['node']['content']['runtime'])
    if title_details['data']['url']['node']['content'].get('credits'):
        actors = []
        for it in title_details['data']['url']['node']['content']['credits']:
            if it['role'] == 'ACTOR':
                actors.append(it['name'])
        item['content_html'] += '<br/><small>Cast: {}'.format(', '.join(actors[:3]))
        if len(actors) > 3:
            item['content_html'] += ' ...'
        item['content_html'] += '</small>'
    item['content_html'] += '</td></tr>'

    title_offers = get_title_offers(item['id'], headers)
    if title_offers:
        if save_debug:
            utils.write_file(title_offers, './debug/data.json')
        if title_offers['data']['node'].get('free'):
            offers = []
            for it in title_offers['data']['node']['free']:
                offers.append('<a href="{}">{}</a>'.format(it['standardWebURL'], it['package']['clearName']))
            item['content_html'] += '<tr><td colspan="2"><b>Watch:</b> {}</td></tr>'.format(', '.join(offers))
        if title_offers['data']['node'].get('flatrate'):
            offers = []
            for it in title_offers['data']['node']['flatrate']:
                offers.append('<a href="{}">{}</a>'.format(it['standardWebURL'], it['package']['clearName']))
            item['content_html'] += '<tr><td colspan="2"><b>Stream:</b> {}</td></tr>'.format(', '.join(offers))
        if title_offers['data']['node'].get('rent'):
            offers = []
            for it in title_offers['data']['node']['rent']:
                offers.append('<a href="{}">{}</a> ({})'.format(it['standardWebURL'], it['package']['clearName'], it['retailPrice']))
            item['content_html'] += '<tr><td colspan="2"><b>Rent:</b> {}</td></tr>'.format(', '.join(offers))
        if title_offers['data']['node'].get('buy'):
            offers = []
            for it in title_offers['data']['node']['buy']:
                offers.append('<a href="{}">{}</a> ({})'.format(it['standardWebURL'], it['package']['clearName'], it['retailPrice']))
            item['content_html'] += '<tr><td colspan="2"><b>Buy:</b> {}</td></tr>'.format(', '.join(offers))
    item['content_html'] += '</table>'
    return item


def get_feed(args, save_debug=False):
    return None
