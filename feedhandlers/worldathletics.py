import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config
from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    gql_headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"123\", \"Not:A-Brand\";v=\"8\", \"Chromium\";v=\"123\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "x-amz-user-agent": "aws-amplify/3.0.2",
        "x-api-key": site_json['graphql']['apiKey']
    }
    gql_data = {
        "operationName": "GetNewArticle",
        "variables": {
            "language": "en",
            "urlSlug": paths[-1]
        },
        "query": "query GetNewArticle($urlSlug: String!, $language: String = \"en\") {\n  getNewArticle(urlSlug: $urlSlug, language: $language) {\n    language\n    ...ArticleUrlFields\n    id\n    title\n    seoTitle\n    body\n    standFirst\n    urlSlug\n    standfirst\n    imageEdited\n    backgroundColour\n    tags\n    metaDescription: seoDescription\n    seoDescription\n    sEOTitle: seoTitle\n    seoTitle\n    liveFrom\n    liveBlog\n    columns\n    mediaIds\n    imageEdited\n    relatedMedia {\n      id\n      fileName\n      copyright\n      title\n      __typename\n    }\n    event {\n      ...ArticleEventUrlFields\n      __typename\n    }\n    relatedEventIds\n    relatedEvents {\n      id\n      name\n      ...ArticleEventUrlFields\n      __typename\n    }\n    relatedCompetitorIds\n    relatedCompetitors {\n      id\n      iaafId\n      firstName\n      lastName\n      friendlyName\n      fullName\n      friendlyNameLetter\n      friendlyNameFirst3Letter\n      sexCode\n      sexName\n      countryCode\n      countryName\n      birthDate\n      birthPlace\n      birthPlaceCountryName\n      sexNameUrlSlug\n      countryUrlSlug\n      birthPlaceCountryUrlSlug\n      birthCountryCode\n      primaryMediaId\n      primaryMedia {\n        fileName\n        __typename\n      }\n      urlSlug\n      representativeId\n      biography\n      twitterLink\n      instagramLink\n      facebookLink\n      transfersOfAllegiance\n      aaId\n      countryFullName\n      familyName\n      givenName\n      birthDateStr\n      facebookUsername\n      twitterUsername\n      instagramUsername\n      __typename\n    }\n    relatedCompetitionIds\n    relatedCompetitions {\n      ...ArticleRelatedCompetitions\n      __typename\n    }\n    relatedArticleIds\n    relatedArticles {\n      ...RelatedArticle\n      __typename\n    }\n    relatedDisciplineCodesWithSex\n    relatedDisciplineCodes\n    relatedDiscipline {\n      id\n      name\n      nameUrlSlug\n      typeNameUrlSlug\n      __typename\n    }\n    relatedDisciplineStats {\n      discipline {\n        disciplineName\n        disciplineCode\n        sexName\n        urlSlug\n        isRelay\n        __typename\n      }\n      seasonBest {\n        aaId\n        result\n        urlSlug\n        achiever\n        nationality\n        resultScore\n        achieverPosition\n        __typename\n      }\n      previousMedalists {\n        name\n        typeId\n        resultMark\n        countryCode\n        urlSlug\n        countryUrlSlug\n        linkUrl\n        __typename\n      }\n      records {\n        categoryId\n        resultMark\n        name\n        countryCode\n        urlSlug\n        linkUrl\n        pending\n        __typename\n      }\n      timetable {\n        isPointsPublished\n        isResultPublished\n        isStartlistPublished\n        phaseDateAndTime\n        phaseNameUrlSlug\n        phaseName\n        phaseOrder\n        phaseSessionName\n        phaseSessionOrder\n        primaryPhaseOrder\n        sexCode\n        sexName\n        sexNameUrlSlug\n        status\n        isPhaseSummaryPublished\n        urlSlug\n        __typename\n      }\n      results {\n        date\n        day\n        race\n        raceId\n        raceNumber\n        results {\n          competitor {\n            teamMembers {\n              id\n              name\n              iaafId\n              urlSlug\n              __typename\n            }\n            id\n            name\n            iaafId\n            urlSlug\n            birthDate\n            hasProfile\n            __typename\n          }\n          mark\n          nationality\n          place\n          points\n          qualified\n          records\n          wind\n          remark\n          details {\n            event\n            eventId\n            raceNumber\n            mark\n            wind\n            placeInRound\n            placeInRace\n            points\n            overallPoints\n            placeInRoundByPoints\n            overallPlaceByPoints\n            __typename\n          }\n          __typename\n        }\n        wind\n        __typename\n      }\n      __typename\n    }\n    relatedLinks {\n      url\n      title: displayText\n      __typename\n    }\n    relatedArticlesBackgroundColor\n    contentModules {\n      moduleType\n      backgroundColor\n      title\n      locations {\n        location {\n          name\n          latitude\n          longitude\n          __typename\n        }\n        headline\n        description\n        link\n        imageEdited\n        __typename\n      }\n      layout\n      videoIds\n      videoPlaylistId\n      videoId\n      slug\n      tagId\n      relatedVideos {\n        id\n        contentId\n        publishedById\n        publishedByName\n        published\n        language\n        gatedContent\n        campaignId\n        tags\n        title\n        thumbnailId\n        thumbnailEdited\n        videoId\n        playerId\n        signedInCTA\n        signedOutCTA\n        thumbnailTitle\n        standFirst\n        __typename\n      }\n      relatedVideo {\n        id\n        contentId\n        publishedById\n        publishedByName\n        published\n        language\n        gatedContent\n        campaignId\n        tags\n        title\n        thumbnailId\n        thumbnailEdited\n        videoId\n        playerId\n        signedInCTA\n        signedOutCTA\n        thumbnailTitle\n        __typename\n      }\n      __typename\n    }\n    gatedContent\n    __typename\n  }\n}\n\nfragment RelatedArticle on NewArticle {\n  ...ArticleUrlFields\n  id\n  title\n  mediaIds\n  imageEdited\n  standFirst\n  relatedMedia {\n    fileName\n    __typename\n  }\n  event {\n    ...ArticleEventUrlFields\n    __typename\n  }\n  relatedEvents {\n    ...ArticleEventUrlFields\n    __typename\n  }\n  __typename\n}\n\nfragment ArticleUrlFields on NewArticle {\n  articleType\n  urlSlug\n  relatedMinisiteIds\n  relatedMinisitePages {\n    slug\n    __typename\n  }\n  tags\n  __typename\n}\n\nfragment ArticleEventUrlFields on WAWEvent {\n  id\n  eventId_WA\n  nameUrlSlug\n  subCategoryNameUrlSlug\n  categoryCode\n  endDate\n  name\n  countryName\n  venue\n  areaName\n  areaCode\n  countryCode\n  indoorOutdoor\n  categoryCode\n  categoryName\n  page {\n    slug\n    __typename\n  }\n  __typename\n}\n\nfragment ArticleRelatedCompetitions on Competition {\n  id\n  name\n  urlSlug\n  category\n  __typename\n}\n"
    }
    gql_json = utils.post_url(site_json['graphql']['endpoint'], json_data=gql_data, headers=gql_headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    return get_article(gql_json['data']['getNewArticle'], url, args, site_json, save_debug)


def get_article(article_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['liveFrom'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    m = re.search(r'<p><strong>(.*?) for World Athletics</strong></p>', article_json['body'])
    if m:
        item['author'] = {"name": m.group(1)}
    else:
        item['author'] = {"name": "World Athletics"}

    item['tags'] = []
    if article_json.get('relatedCompetitors'):
        for it in article_json['relatedCompetitors']:
            item['tags'].append(it['fullName'])
    if article_json.get('relatedDiscipline'):
        for it in article_json['relatedDiscipline']:
            item['tags'].append(it['name'])
    if article_json.get('relatedCompetitions'):
        for it in article_json['relatedCompetitions']:
            item['tags'].append(it['name'])
    if article_json.get('relatedEvents'):
        for it in article_json['relatedEvents']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if article_json.get('tags'):
        item['tags'] += article_json['tags'].copy()

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    item['content_html'] = ''

    if article_json.get('relatedMedia'):
        item['_image'] = 'https://assets.aws.worldathletics.org/' + article_json['relatedMedia'][0]['fileName']
        if article_json['relatedMedia'][0].get('title'):
            caption = article_json['relatedMedia'][0]['title']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)
    elif article_json.get('imageEdited'):
        item['_image'] = 'https://assets.aws.worldathletics.org/' + article_json['imageEdited']
        item['content_html'] += utils.add_image(item['_image'])

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    for el in soup.find_all('div', recursive=False):
        new_html = ''
        if el.img:
            it = el.find('p')
            if it:
                caption = it.decode_contents()
            else:
                caption = ''
            new_html = utils.add_image(el.img['src'], caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled div in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_='instagram-media'):
        new_html = utils.add_embed(el['data-instgrm-permalink'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    gql_headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"123\", \"Not:A-Brand\";v=\"8\", \"Chromium\";v=\"123\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "x-amz-user-agent": "aws-amplify/3.0.2",
        "x-api-key": site_json['graphql']['apiKey']
    }
    gql_data = {
        "operationName": "GetNewArticles",
        "variables": {
            "language": "en",
            "orderBy": "PublishedDate",
            "orderDirection": "Descending",
            "checkHiddenOnMainSite": True,
            "offset": 0,
            "limit": 12
        },
        "query": "query GetNewArticles($language: String = \"en\", $relatedEventIds: [Int], $relatedCompetitionIds: [String], $types: [Int], $orderBy: OrderByNewArticleEnum = PublishedDate, $orderDirection: OrderDirectionEnum = Descending, $limit: Int, $offset: Int, $relatedEventNameUrlSlug: [String], $relatedDisciplineUrlSlug: [String], $relatedDisciplineCodes: [String], $relatedAthleteUrlSlug: [String], $relatedAthleteIds: [String], $relatedCompetitionUrlSlug: [String], $relatedMinisiteIds: [String], $relatedLocationIds: [String], $relatedCountryCodes: [String], $relatedRegionCodes: [String], $tags: [String], $filterArticleSlug: String, $checkHiddenOnMainSite: Boolean = true, $publishedYear: String) {\n  getNewArticles(language: $language, relatedEventIds: $relatedEventIds, relatedCompetitionIds: $relatedCompetitionIds, relatedEventNameUrlSlug: $relatedEventNameUrlSlug, relatedDisciplineUrlSlug: $relatedDisciplineUrlSlug, relatedDisciplineCodes: $relatedDisciplineCodes, relatedAthleteUrlSlug: $relatedAthleteUrlSlug, relatedAthleteIds: $relatedAthleteIds, relatedCompetitionUrlSlug: $relatedCompetitionUrlSlug, relatedMinisiteIds: $relatedMinisiteIds, relatedLocationIds: $relatedLocationIds, relatedCountryCodes: $relatedCountryCodes, relatedRegionCodes: $relatedRegionCodes, tags: $tags, types: $types, orderBy: $orderBy, orderDirection: $orderDirection, limit: $limit, offset: $offset, filterArticleSlug: $filterArticleSlug, checkHiddenOnMainSite: $checkHiddenOnMainSite, publishedYear: $publishedYear) {\n    ...ArticleUrlFields\n    id\n    title\n    body\n    gatedContent\n    standFirst\n    standfirst\n    liveFrom\n    contentId\n    urlSlug\n    backgroundColour\n    seoDescription\n    imageEdited\n    campaignId\n    relatedUrls\n    slug\n    articleType\n    featureImageId\n    featureImageEdited\n    hideOnTheMainSite\n    sEOTitle: seoTitle\n    seoTitle\n    metaDescription: seoDescription\n    eventId\n    blogUpdated\n    liveBlog\n    language\n    contentModules {\n      moduleType\n      backgroundColor\n      __typename\n    }\n    relatedMedia {\n      id\n      fileName\n      __typename\n    }\n    relatedCompetitions {\n      ...ArticleRelatedCompetitions\n      __typename\n    }\n    event {\n      ...ArticleEventUrlFields\n      __typename\n    }\n    relatedEventIds\n    relatedEvents {\n      id\n      name\n      ...ArticleEventUrlFields\n      __typename\n    }\n    relatedCompetitors {\n      id\n      iaafId\n      firstName\n      lastName\n      friendlyName\n      fullName\n      friendlyNameLetter\n      friendlyNameFirst3Letter\n      sexCode\n      sexName\n      countryCode\n      countryName\n      birthDate\n      birthPlace\n      birthPlaceCountryName\n      sexNameUrlSlug\n      countryUrlSlug\n      birthPlaceCountryUrlSlug\n      birthCountryCode\n      primaryMediaId\n      primaryMedia {\n        fileName\n        __typename\n      }\n      urlSlug\n      representativeId\n      biography\n      twitterLink\n      instagramLink\n      facebookLink\n      transfersOfAllegiance\n      aaId\n      countryFullName\n      familyName\n      givenName\n      birthDateStr\n      facebookUsername\n      twitterUsername\n      instagramUsername\n      __typename\n    }\n    relatedCountryCodes\n    relatedRegionCodes\n    __typename\n  }\n}\n\nfragment ArticleUrlFields on NewArticle {\n  articleType\n  urlSlug\n  relatedMinisiteIds\n  relatedMinisitePages {\n    slug\n    __typename\n  }\n  tags\n  __typename\n}\n\nfragment ArticleEventUrlFields on WAWEvent {\n  id\n  eventId_WA\n  nameUrlSlug\n  subCategoryNameUrlSlug\n  categoryCode\n  endDate\n  name\n  countryName\n  venue\n  areaName\n  areaCode\n  countryCode\n  indoorOutdoor\n  categoryCode\n  categoryName\n  page {\n    slug\n    __typename\n  }\n  __typename\n}\n\nfragment ArticleRelatedCompetitions on Competition {\n  id\n  name\n  urlSlug\n  category\n  __typename\n}\n"
    }
    if len(paths) > 0:
        if paths[0] == 'news':
            if len(paths) > 1:
                if paths[1] == 'news':
                    gql_data['variables']['types'] = [0]
                elif paths[1] == 'previews':
                    gql_data['variables']['types'] = [2]
                elif paths[1] == 'reports':
                    gql_data['variables']['types'] = [3]
                elif paths[1] == 'press-releases':
                    gql_data['variables']['types'] = [4]
                elif paths[1] == 'features':
                    gql_data['variables']['types'] = [5]
                elif paths[1] == 'series':
                    gql_data['variables']['types'] = [6]
            else:
                gql_data['variables']['types'] = [0, 1, 2, 3, 4, 5, 6, 7, 8]
        elif paths[0] == 'personal-best':
            if len(paths) > 1:
                if paths[1] == 'lifestyle':
                    gql_data['variables']['types'] = [9]
                elif paths[1] == 'performance':
                    gql_data['variables']['types'] = [10]
                elif paths[1] == 'culture':
                    gql_data['variables']['types'] = [11]
                elif paths[1] == 'all':
                    gql_data['variables']['types'] = [9, 10, 11]
            else:
                gql_data['variables']['types'] = [9, 10, 11]
        elif paths[0] == 'athletics-better-world':
            if len(paths) > 1:
                if paths[1] == 'news':
                    gql_data['variables']['relatedMinisiteIds'] = ['614ae7f5443a96af63970f10']
                    gql_data['variables']['types'] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
                elif paths[1] == 'sustainability':
                    gql_data['variables']['tags'] = ['sustainability']
                    gql_data['variables']['types'] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
                elif paths[1] == 'athlete-refugee-team':
                    gql_data['variables']['tags'] = ['refugee_team']
                    gql_data['variables']['types'] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    gql_json = utils.post_url(site_json['graphql']['endpoint'], json_data=gql_data, headers=gql_headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['getNewArticles']:
        if article['articleType'] == 0:
            article_type = 'news'
        elif article['articleType'] == 2:
            article_type = 'previews'
        elif article['articleType'] == 3:
            article_type = 'reports'
        elif article['articleType'] == 4:
            article_type = 'press-releases'
        elif article['articleType'] == 5:
            article_type = 'features'
        elif article['articleType'] == 6:
            article_type = 'series'
        else:
            article_type = 'news'
        article_url = 'https://' + split_url.netloc
        if article.get('relatedMinisitePages'):
            article_url += '/{}/news/'.format(article['relatedMinisitePages'][0]['slug'])
        elif article.get('event'):
            article_url += '/competitions/' + article['event']['subCategoryNameUrlSlug']
            if article['event'].get('page'):
                article_url += '/{}/news/{}/'.format(article['event']['page']['slug'], article_type)
            else:
                article_url += '/news/'
        elif article.get('relatedCompetitions'):
            article_url += '/competitions/{}/news/'.format(article['relatedCompetitions'][0]['urlSlug'])
        else:
            article_url += '/news/{}/'.format(article_type)
        article_url += article['urlSlug']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_article(article, article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    # feed['title'] =
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
