import re
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import bustle, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    gql_query = {
        "operationName": "Article",
        "query": "\n  query Article($input: ArticleInput!) {\n    article(input: $input) {\n      authors {\n        avatar {\n          credit\n          edition\n          height\n          id\n          src\n          title\n          type\n          width\n        }\n        bio\n        email\n        facebook\n        id\n        instagram\n        linkedIn\n        name\n        slug\n        title\n        tikTok\n        twitter\n      }\n      category {\n        id\n        name\n        pathname\n      }\n      content\n      cpmTags {\n        entity\n        topic\n        tax\n      }\n      customSchema {\n        author\n        brand\n        description\n        dateModified\n        datePublished\n        name\n        ratingValue\n      }\n      description\n      editorsNote\n      featuredImage {\n        credit\n        height\n        id\n        src\n        title\n        width\n      }\n      id\n      isTragedy\n      link {\n        href\n        hreflang\n        rel\n      }\n      pathname\n      published\n      readingTime {\n        minutes\n        text\n      }\n      reviewAffiliate {\n        buttonText\n        circuitId\n        cta\n        name\n        startingPrice\n        subheading\n      }\n      reviewedBy {\n        avatar {\n          credit\n          edition\n          height\n          id\n          src\n          title\n          type\n          width\n        }\n        bio\n        email\n        facebook\n        id\n        instagram\n        linkedIn\n        name\n        slug\n        title\n        tikTok\n        twitter\n      }\n      showAds\n      seal {\n        kind\n        redirectSrc\n        year\n      }\n      showEditorialDisclaimer\n      slots\n      slug\n      socialThumbnails {\n        facebook\n        twitter\n      }\n      sponsorship {\n        logoUrl\n        name\n        showLeaderboard\n        showRightRail\n        text\n        url\n      }\n      summary\n      surrogateKeys\n      tableOfContents {\n        id\n        title\n      }\n      title\n      titleTag\n      tpSrc\n      updated\n      wpPostId\n    }\n  }\n",
        "variables": {
            "input": {
                "edition": "US",
                "slug": paths[-1],
                "shouldShowPreview": False
            }
        }
    }
    gql_json = utils.post_url('https://empennage.api.thepointsguy.com/graphql', json_data=gql_query)
    if not gql_json:
        return None

    article_json = gql_json['data']['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://thepointsguy.com' + article_json['pathname']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updated'):
        dt = datetime.fromisoformat(article_json['updated'])
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    item['tags'].append(article_json['category']['name'])
    if article_json.get('cpmTags'):
        if article_json['cpmTags'].get('tax'):
            item['tags'] += list(map(str.strip, article_json['cpmTags']['tax'].split(',')))
        if article_json['cpmTags'].get('topic'):
            item['tags'] += list(map(str.strip, article_json['cpmTags']['topic'].split(',')))

    if article_json.get('description'):
        item['summary'] = article_json['description']

    item['content_html'] = ''
    if article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']['src']
        captions = []
        if article_json['featuredImage'].get('caption'):
            captions.append(article_json['featuredImage']['caption'])
        if article_json['featuredImage'].get('credit'):
            captions.append(article_json['featuredImage']['credit'])
        if not captions and article_json['featuredImage'].get('title') and not re.search(r'\d+-IMG_\d+|screenshot', article_json['featuredImage']['title'], flags=re.I):
            captions.append(article_json['featuredImage']['title'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    item['content_html'] += bustle.render_body(article_json['content'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
