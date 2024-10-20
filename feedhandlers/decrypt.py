import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_term_definition(slug):
    gql_query = {
        "operationName": "Terms",
        "variables": {
            "filters": {
                "taxonomy": {
                    "eq": "DEFINITION"
                },
                "slug": {
                    "eq": slug
                }
            },
            "pagination": {
                "pageSize": 1
            }
        },
        "query": '\n  query Terms(\n    $filters: TermEntityFilterInput\n    $pagination: PaginationArg\n    $sort: [String]\n  ) {\n    terms(filters: $filters, pagination: $pagination, sort: $sort) {\n      data {\n        ...TermSharedData\n        ... on CategoryTermEntity {\n          parent {\n            data {\n              id\n              slug\n              name\n            }\n          }\n        }\n        ... on CollectionTermEntity {\n          articlesCount\n          articles(pagination: { pageSize: 4 }, sort: "publishedAt:desc") {\n            data {\n              featuredImage {\n                src\n                alt\n                width\n                height\n              }\n            }\n          }\n        }\n        ... on DefinitionTermEntity {\n          guide {\n            data {\n              id\n              slug\n              locale\n            }\n          }\n        }\n      }\n      pagination {\n        page\n        pageCount\n        pageSize\n        total\n      }\n    }\n  }\n\n  fragment TermSharedData on TermEntity {\n    __typename\n    id\n    slug\n    taxonomy\n    name\n    description\n  }\n'
    }
    gql_json = utils.post_url('https://gateway.decrypt.co/', json_data=gql_query)
    if not gql_json:
        return None
    return gql_json['data']['terms']['data'][0]


def get_content(url, args, site_json, save_debug=False):
    article_json = None
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0].isnumeric():
        gql_query = {
            "operationName": "ArticlePage",
            "variables": {
                "locale": "en",
                "filters": {
                    "id": {
                        "eq": int(paths[0])
                    },
                    "locale": {
                        "eq": "en"
                    }
                }
            },
            "query": '\n  query ArticlePage($locale: Locale!, $filters: ArticleEntityFilterInput) {\n    articles(filters: $filters, pagination: { pageSize: 1 }) {\n      data {\n        __typename\n        id\n        slug\n        status\n        locale\n        title\n        excerpt\n        blurb\n        content\n        tldrTitle\n        tldrContent\n        readingTime\n        readNext\n        publishedAt\n        modifiedAt\n        featuredImage {\n          src\n          alt\n          width\n          height\n        }\n        sponsor {\n          name\n          url\n        }\n        meta {\n          image\n          title\n          description\n          ogTitle\n          ogDescription\n          twitterTitle\n          twitterDescription\n          hreflangs {\n            hreflang\n            path\n          }\n        }\n        authors {\n          data {\n            __typename\n            id\n            slug\n            name\n            roles\n            avatar {\n              src\n              alt\n              width\n              height\n            }\n          }\n        }\n        category {\n          data {\n            ...TermSharedData\n            parent {\n              data {\n                ...TermSharedData\n              }\n            }\n          }\n        }\n        collections {\n          data {\n            ...TermSharedData\n            articles(\n              filters: { locale: { eq: $locale } }\n              pagination: { pageSize: 4 }\n              sort: ["publishedAt:desc"]\n            ) {\n              data {\n                featuredImage {\n                  src\n                  alt\n                  width\n                  height\n                }\n              }\n            }\n          }\n        }\n        distinctions {\n          data {\n            ...TermSharedData\n          }\n        }\n        tags {\n          data {\n            ...TermSharedData\n            channel\n          }\n        }\n        celebrities {\n          data {\n            ...CelebritySharedData\n          }\n        }\n        coins {\n          data {\n            ...CoinSharedData\n          }\n        }\n        ... on CourseArticleEntity {\n          courses {\n            data {\n              ...CourseData\n            }\n          }\n        }\n        ... on LearnArticleEntity {\n          courses {\n            data {\n              ...CourseData\n            }\n          }\n        }\n      }\n    }\n  }\n\n  fragment TermSharedData on TermEntity {\n    __typename\n    id\n    slug\n    taxonomy\n    name\n    description\n  }\n\n  fragment CelebritySharedData on CelebrityEntity {\n    __typename\n    id\n    slug\n    status\n    name\n    description\n    role\n    birthday\n    location\n    education\n    currentProjects\n    previousProjects\n    twitter\n    linkedin\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n  }\n\n  fragment CoinSharedData on CoinEntity {\n    __typename\n    id\n    slug\n    name\n    description\n    apiId\n    symbol\n    color\n    website\n    itb_slug\n    topperNetwork\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n  }\n\n  fragment CourseData on CourseEntity {\n    ...CourseSharedData\n    articles(pagination: { pageSize: 100 }) {\n      data {\n        __typename\n        ...ArticleSharedData\n      }\n      pagination {\n        total\n      }\n    }\n  }\n\n  fragment CourseSharedData on CourseEntity {\n    __typename\n    id\n    slug\n    status\n    locale\n    name\n    description\n    readingTime\n    publishedAt\n    modifiedAt\n    quiz\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n    sponsor {\n      name\n      url\n      logo_light {\n        src\n        alt\n        width\n        height\n      }\n      logo_dark {\n        src\n        alt\n        width\n        height\n      }\n    }\n  }\n\n  fragment ArticleSharedData on ArticleEntity {\n    __typename\n    id\n    slug\n    locale\n    status\n    title\n    excerpt\n    blurb\n    readingTime\n    publishedAt\n    modifiedAt\n    tags {\n      data {\n        description\n        id\n        name\n        slug\n        taxonomy\n        channel\n      }\n    }\n    featuredVideoUrl\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n    sponsor {\n      name\n      url\n    }\n    meta {\n      hreflangs {\n        hreflang\n        path\n      }\n    }\n    authors {\n      data {\n        __typename\n        id\n        slug\n        name\n        roles\n      }\n    }\n    category {\n      data {\n        __typename\n        id\n        slug\n        name\n        parent {\n          data {\n            __typename\n            id\n            slug\n            name\n          }\n        }\n      }\n    }\n    distinctions {\n      data {\n        __typename\n        id\n        slug\n        name\n      }\n    }\n    collections {\n      data {\n        __typename\n        id\n        slug\n        name\n        title\n        subtitle\n      }\n    }\n    coins {\n      data {\n        __typename\n        id\n        slug\n        name\n        symbol\n        color\n      }\n    }\n    ... on ReviewArticleEntity {\n      rating\n    }\n  }\n'
        }
        gql_json = utils.post_url('https://gateway.decrypt.co/', json_data=gql_query)
        if not gql_json:
            return None
        article_json = gql_json['data']['articles']['data'][0]
    else:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                article_json = next_data['props']['pageProps']['post']
    if not article_json:
        logger.warning('unhandled url ' + url)
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    return get_item(article_json, url, args, site_json, save_debug)


def get_item(article_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://decrypt.co/{}/{}'.format(article_json['id'], article_json['slug'])
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modifiedAt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in article_json['authors']['data']]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    item['tags'] = []
    if article_json['category'].get('data'):
        item['tags'].append(article_json['category']['data']['name'])
    if article_json['tags'].get('data'):
        for it in article_json['tags']['data']:
            item['tags'].append(it['name'])
    if article_json['collections'].get('data'):
        for it in article_json['collections']['data']:
            item['tags'].append(it['name'])
    if article_json['coins'].get('data'):
        for it in article_json['coins']['data']:
            item['tags'].append(it['name'])
    if article_json['celebrities'].get('data'):
        for it in article_json['celebrities']['data']:
            item['tags'].append(it['name'])
    if item.get('tags'):
        # Remove duplicates (case-insensitive)
        item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))
    else:
        del item['tags']

    item['content_html'] = ''
    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['excerpt'])

    if article_json.get('featuredImage'):
        item['image'] = article_json['featuredImage']['src']
        item['content_html'] += utils.add_image(article_json['featuredImage']['src'], article_json['featuredImage'].get('alt'))

    if article_json.get('tldrContent'):
        item['content_html'] += '<h3>{}</h3>{}<div>&nbsp;</div><hr/><div>&nbsp;</div>'.format(article_json['tldrTitle'], article_json['tldrContent'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    soup = BeautifulSoup(article_json['content'], 'html.parser')
    for el in reversed(soup.find_all('span', class_='definition')):
        link = ''
        new_html = ''
        if el.get('link'):
            query = parse_qs(urlsplit(el['link']).query)
            if query.get('p'):
                link = 'https://decrypt.co/' + query['p'][0]
        if el.get('slug'):
            term_json = get_term_definition(el['slug'])
            if term_json:
                if term_json.get('guide') and term_json['guide'].get('data'):
                    link = 'https://decrypt.co/{}'.format(term_json['guide']['data']['id'])
                if term_json.get('description'):
                    if link:
                        new_html = utils.add_blockquote('<div style="font-size:1.1em; font-weight:bold;">ⓘ <a href="{}">{}</a></div><p>{}</p>'.format(link, term_json['name'].title(), term_json['description']))
                    else:
                        new_html = utils.add_blockquote('<div style="font-size:1.1em; font-weight:bold;">ⓘ {}</div><p>{}</p>'.format(term_json['name'].title(), term_json['description']))
        if link and el.a:
            el.a.attrs = {}
            el.a['href'] = link
        # else:
        #     el.attrs = {}
        #     el.name = 'u'
        if new_html:
            it = el.find_parent('p')
            if it:
                new_el = BeautifulSoup(new_html, 'html.parser')
                it.insert_after(new_el)
        if not link and not new_html:
            logger.warning('unhandled definition link ' + str(el))
        else:
            el.unwrap()

    for el in soup.find_all(class_='embedded-post'):
        # TODO: delete these??
        new_html = utils.add_embed(el.a['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    item['content_html'] += wp_posts.format_content(str(soup), item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    gql_query = {
        "operationName": "ArticlePreviews",
        "query": '\n  query ArticlePreviews(\n    $locale: Locale!, $filters: ArticleEntityFilterInput\n    $pagination: PaginationArg\n    $sort: [String]\n  ) {\n    articles(filters: $filters, pagination: $pagination, sort: $sort) {\n      data {\n        __typename\n        id\n        slug\n        status\n        locale\n        title\n        excerpt\n        blurb\n        content\n        tldrTitle\n        tldrContent\n        readingTime\n        readNext\n        publishedAt\n        modifiedAt\n        featuredImage {\n          src\n          alt\n          width\n          height\n        }\n        sponsor {\n          name\n          url\n        }\n        meta {\n          image\n          title\n          description\n          ogTitle\n          ogDescription\n          twitterTitle\n          twitterDescription\n          hreflangs {\n            hreflang\n            path\n          }\n        }\n        authors {\n          data {\n            __typename\n            id\n            slug\n            name\n            avatar {\n              src\n              alt\n              width\n              height\n            }\n          }\n        }\n        category {\n          data {\n            ...TermSharedData\n            parent {\n              data {\n                ...TermSharedData\n              }\n            }\n          }\n        }\n        collections {\n          data {\n            ...TermSharedData\n            articles(\n              filters: { locale: { eq: $locale } }\n              pagination: { pageSize: 4 }\n              sort: ["publishedAt:desc"]\n            ) {\n              data {\n                featuredImage {\n                  src\n                  alt\n                  width\n                  height\n                }\n              }\n            }\n          }\n        }\n        distinctions {\n          data {\n            ...TermSharedData\n          }\n        }\n        tags {\n          data {\n            ...TermSharedData\n            channel\n          }\n        }\n        celebrities {\n          data {\n            ...CelebritySharedData\n          }\n        }\n        coins {\n          data {\n            ...CoinSharedData\n          }\n        }\n        ... on CourseArticleEntity {\n          courses {\n            data {\n              ...CourseData\n            }\n          }\n        }\n        ... on LearnArticleEntity {\n          courses {\n            data {\n              ...CourseData\n            }\n          }\n        }\n      }\n    }\n  }\n\n  fragment TermSharedData on TermEntity {\n    __typename\n    id\n    slug\n    taxonomy\n    name\n    description\n  }\n\n  fragment CelebritySharedData on CelebrityEntity {\n    __typename\n    id\n    slug\n    status\n    name\n    description\n    role\n    birthday\n    location\n    education\n    currentProjects\n    previousProjects\n    twitter\n    linkedin\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n  }\n\n  fragment CourseSharedData on CourseEntity {\n    __typename\n    id\n    slug\n    status\n    name\n    description\n    readingTime\n    publishedAt\n    modifiedAt\n    quiz\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n    sponsor {\n      name\n      url\n      logo_light {\n        src\n        alt\n        width\n        height\n      }\n      logo_dark {\n        src\n        alt\n        width\n        height\n      }\n    }\n  }\n\n  fragment CourseData on CourseEntity {\n    ...CourseSharedData\n    articles(pagination: { pageSize: 100 }) {\n      data {\n        __typename\n        ...ArticleSharedData\n      }\n      pagination {\n        total\n      }\n    }\n  }\n\n  fragment CoinSharedData on CoinEntity {\n    __typename\n    id\n    slug\n    name\n    description\n    apiId\n    symbol\n    color\n    website\n    itb_slug\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n  }\n\n  fragment ArticleSharedData on ArticleEntity {\n    __typename\n    id\n    slug\n    locale\n    status\n    title\n    excerpt\n    blurb\n    readingTime\n    publishedAt\n    modifiedAt\n    tags {\n      data {\n        description\n        id\n        name\n        slug\n        taxonomy\n        channel\n      }\n    }\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n    sponsor {\n      name\n      url\n    }\n    meta {\n      hreflangs {\n        hreflang\n        path\n      }\n    }\n    authors {\n      data {\n        __typename\n        id\n        slug\n        name\n      }\n    }\n    category {\n      data {\n        __typename\n        id\n        slug\n        name\n        parent {\n          data {\n            __typename\n            id\n            slug\n            name\n          }\n        }\n      }\n    }\n    distinctions {\n      data {\n        __typename\n        id\n        slug\n        name\n      }\n    }\n    collections {\n      data {\n        __typename\n        id\n        slug\n        name\n        title\n        subtitle\n      }\n    }\n    coins {\n      data {\n        __typename\n        id\n        slug\n        name\n        symbol\n        color\n      }\n    }\n    ... on ReviewArticleEntity {\n      rating\n    }\n  }\n'
    }
    # "query": "\n  query ArticlePreviews(\n    $filters: ArticleEntityFilterInput\n    $pagination: PaginationArg\n    $sort: [String]\n  ) {\n    articles(filters: $filters, pagination: $pagination, sort: $sort) {\n      data {\n        ...ArticleSharedData\n      }\n      pagination {\n        page\n        pageCount\n        pageSize\n        total\n      }\n    }\n  }\n\n  fragment ArticleSharedData on ArticleEntity {\n    __typename\n    id\n    slug\n    locale\n    status\n    title\n    excerpt\n    blurb\n    readingTime\n    publishedAt\n    modifiedAt\n    tags {\n      data {\n        description\n        id\n        name\n        slug\n        taxonomy\n        channel\n      }\n    }\n    featuredVideoUrl\n    featuredImage {\n      src\n      alt\n      width\n      height\n    }\n    sponsor {\n      name\n      url\n    }\n    meta {\n      hreflangs {\n        hreflang\n        path\n      }\n    }\n    authors {\n      data {\n        __typename\n        id\n        slug\n        name\n        roles\n      }\n    }\n    category {\n      data {\n        __typename\n        id\n        slug\n        name\n        parent {\n          data {\n            __typename\n            id\n            slug\n            name\n          }\n        }\n      }\n    }\n    distinctions {\n      data {\n        __typename\n        id\n        slug\n        name\n      }\n    }\n    collections {\n      data {\n        __typename\n        id\n        slug\n        name\n        title\n        subtitle\n      }\n    }\n    coins {\n      data {\n        __typename\n        id\n        slug\n        name\n        symbol\n        color\n      }\n    }\n    ... on ReviewArticleEntity {\n      rating\n    }\n  }\n"

    if len(paths) == 0:
        return rss.get_feed('https://decrypt.co/feed', args, site_json, save_debug, get_content)
    elif paths[-1] == 'feed':
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    elif paths[0] == 'author':
        gql_query['variables'] = {
            "locale": "en",
            "filters": {
                "locale": {
                    "eq": "en"
                },
                "authors": {
                    "slug": {
                        "eq": paths[-1]
                    }
                }
            },
            "pagination": {
                "pageSize": 10,
                "page": 1
            },
            "sort": [
                "publishedAt:desc"
            ]
        }
    elif paths[0] == 'news' or len(paths) == 1:
        gql_query['variables'] = {
            "locale": "en",
            "filters": {
                "locale": {
                    "eq": "en"
                },
                "category": {
                    "slug": {
                        "eq": paths[-1]
                    }
                }
            },
            "pagination": {
                "pageSize": 10,
                "page": 1
            },
            "sort": [
                "publishedAt:desc"
            ]
        }
    elif len(paths) == 2:
        gql_query['variables'] = {
            "locale": "en",
            "filters": {
                "locale": {
                    "eq": "en"
                },
                "category": {
                    "slug": {
                        "eq": paths[0]
                    }
                },
                "distinctions": {
                    "slug": {
                        "eq": paths[1]
                    }
                }
            },
            "pagination": {
                "pageSize": 10,
                "page": 1
            },
            "sort": [
                "publishedAt:desc"
            ]
        }
    else:
        logger.warning('unsupported feed url ' + url)
        return None

    gql_json = utils.post_url('https://gateway.decrypt.co/', json_data=gql_query)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['articles']['data']:
        article_url = 'https://decrypt.co/{}/{}'.format(article['id'], article['slug'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_item(article, article_url, args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
