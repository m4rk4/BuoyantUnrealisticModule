import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    return 'https://www.theskimm.com/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def add_image(image, width=1080):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(resize_image(image['img']['url']), ' | '.join(captions))


def add_image_embed(entry_id, width=1080):
    data = {
        "query": "query ImageQuery($entryId: String!) {\n  image(id: $entryId, preview: false) {\n    ...ImageFragment\n  }\n}\n\nfragment ImageFragment on Image {\n  __typename\n  img {\n    url\n  }\n  alt\n  href\n  credit\n  placeholderData\n}\n",
        "variables":{
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    return add_image(gql_json['data']['image'], width)


def add_video_embed(entry_id):
    data = {
        "query": "query VideoEmbedQuery($entryId: String!) {\n  videoEmbed(id: $entryId, preview: false) {\n    ...VideoEmbedFragment\n  }\n}\n\nfragment VideoEmbedFragment on VideoEmbed {\n  title\n  src\n}\n",
        "variables":{
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    if True:
        utils.write_file(gql_json, './debug/video.json')
    # sometimes src is repeated
    src = gql_json['data']['videoEmbed']['src'].split(' ')[0]
    # usually only Youtube videos
    return utils.add_embed(src)


def add_social_media_embed(entry_id):
    data = {
        "query": "query SocialMediaEmbedQuery($entryId: String!) {\n  socialMediaEmbed(id: $entryId, preview: false) {\n    ...SocialMediaEmbedFragment\n  }\n}\n\nfragment SocialMediaEmbedFragment on SocialMediaEmbed {\n  __typename\n  title\n  embedType\n  source\n}\n",
        "variables":{
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    return utils.add_embed(gql_json['data']['socialMediaEmbed']['source'])


def add_disclaimer_embed(entry_id):
    data = {
        "query": "query DisclaimerQuery($entryId: String!) {\n  disclaimer(id: $entryId, preview: false) {\n    ...DisclaimerFragment\n  }\n}\n\nfragment DisclaimerFragment on Disclaimer {\n  __typename\n  sys {\n    id\n  }\n  text {\n    ...DisclaimerTextFragment\n  }\n}\n\nfragment DisclaimerTextFragment on DisclaimerText {\n  __typename\n  json\n  links {\n    __typename\n    entries {\n      block {\n        sys {\n          id\n        }\n        ... on Entry {\n          __typename\n          sys {\n            id\n          }\n        }\n        ... on Embed {\n          ...EmbedFragment\n        }\n      }\n      inline {\n        sys {\n          id\n        }\n        ... on Image {\n          __typename\n          sys {\n            id\n          }\n        }\n      }\n    }\n  }\n}\n\nfragment EmbedFragment on Embed {\n  __typename\n  sys {\n    id\n  }\n  title\n  src\n  embedCode\n  fullBleed\n}\n",
        "variables":{
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    content_html = ''
    for content in gql_json['data']['disclaimer']['text']['json']['content']:
        content_html += render_content(content, gql_json['data']['disclaimer']['text']['links'])
    return content_html


def add_commercecard_embed(entry_id):
    data = {
        "query": "query CommerceCardQuery($entryId: String!) {\n  commerceCard(id: $entryId, preview: false) {\n    ...CommerceCardFragment\n  }\n}\n\nfragment CommerceCardFragment on CommerceCard {\n  __typename\n  productTitle\n  productDescription {\n    json\n  }\n  price\n  brand\n  cta\n  credit\n  purchaseUrl\n  sponsored\n  image {\n    __typename\n    url\n  }\n  imageAlt\n  productImage {\n    __typename\n    sys {\n      id\n    }\n    ... on Image {\n      __typename\n      alt\n      img {\n        width\n        height\n        description\n        title\n        url\n      }\n      sys {\n        id\n      }\n    }\n  }\n  sys {\n    id\n  }\n}\n",
        "variables":{
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    card_json = gql_json['data']['commerceCard']
    content_html = ''
    if card_json.get('image'):
        if card_json.get('credit'):
            caption = card_json['credit']
        else:
            caption = ''
        content_html += utils.add_image(resize_image(card_json['image']['url']), caption)
    if card_json.get('productDescription'):
        if card_json['productDescription'].get('links'):
            links = card_json['productDescription']['links']
        else:
            links = None
        for content in card_json['productDescription']['json']['content']:
            content_html += render_content(content, links)
    content_html += '<ul><li><a href="{}">{}</a></li></ul>'.format(card_json['purchaseUrl'], card_json['cta'])
    return content_html


def get_next_json(url):
    tld = tldextract.extract(url)
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '/index.json'

    sites_json = utils.read_json_file('./sites.json')
    build_id = sites_json[tld.domain]['buildId']
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, build_id, path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating buildId')
        page_html = utils.get_url_html('{}://{}'.format(split_url.scheme, split_url.netloc))
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m:
            sites_json[tld.domain]['buildId'] = m.group(1)
            utils.write_file(sites_json, './sites.json')
            next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, m.group(1), path)
            next_json = utils.get_url_json(next_url)
            if not next_json:
                return None
    return next_json


def render_content(node, links):
    content_html = ''
    if node['nodeType'] == 'paragraph':
        content_html += '<p>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</p>'

    elif node['nodeType'] == 'text':
        start_tags = ''
        end_tags = ''
        if node.get('marks'):
            for mark in node['marks']:
                if mark['type'] == 'underline':
                    start_tags += '<u>'
                    end_tags = '</u>' + end_tags
                elif mark['type'] == 'bold':
                    start_tags += '<b>'
                    end_tags = '</b>' + end_tags
                elif mark['type'] == 'italic':
                    start_tags += '<i>'
                    end_tags = '</i>' + end_tags
                else:
                    logger.warning('unhandle mark type ' + mark['type'])
        content_html += start_tags + node['value'] + end_tags

    elif node['nodeType'].startswith('heading'):
        m = re.search(r'heading-(\d)', node['nodeType'])
        content_html += '<h{}>'.format(m.group(1))
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</h{}>'.format(m.group(1))

    elif node['nodeType'] == 'hyperlink':
        content_html += '<a href="{}">'.format(node['data']['uri'])
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</a>'

    elif node['nodeType'] == 'blockquote':
        quote = ''
        for content in node['content']:
            quote += render_content(content, links)
        content_html += utils.add_blockquote(quote)

    elif node['nodeType'] == 'unordered-list':
        content_html += '<ul>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</ul>'

    elif node['nodeType'] == 'ordered-list':
        content_html += '<ol>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</ol>'

    elif node['nodeType'] == 'list-item':
        content_html += '<li>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</li>'

    elif node['nodeType'] == 'embedded-entry-block':
        if node['data']['target']['sys']['type'] == 'Link' and node['data']['target']['sys']['linkType'] == 'Entry':
            link = next((it for it in links['entries']['block'] if it['sys']['id'] == node['data']['target']['sys']['id']), None)
            if link:
                if link['__typename'] == 'Image':
                    content_html += add_image_embed(link['sys']['id'])
                elif link['__typename'] == 'VideoEmbed':
                    content_html += add_video_embed(link['sys']['id'])
                elif link['__typename'] == 'SocialMediaEmbed':
                    content_html += add_social_media_embed(link['sys']['id'])
                elif link['__typename'] == 'Disclaimer':
                    content_html += add_disclaimer_embed(link['sys']['id'])
                elif link['__typename'] == 'CommerceCard':
                    content_html += add_commercecard_embed(link['sys']['id'])
                elif link['__typename'] == 'Embed':
                    if link.get('src'):
                        content_html += utils.add_embed(link['src'])
                    else:
                        soup = BeautifulSoup(link['embedCode'], 'html.parser')
                        it = soup.find('iframe')
                        if it:
                            content_html += utils.add_embed(it['src'])
                        else:
                            logger.warning('unhandled embedded-entry-block link type Embed ' + link['title'])
                elif link['__typename'] == 'AdUnit' or link['__typename'] == 'MarketingModule':
                    pass
                else:
                    logger.warning('unhandled embedded-entry-block link type ' + link['__typename'])
            else:
                logger.warning('unable to find embedded-entry-block link entry')
        else:
            logger.warning('unhandled embedded-entry-block')

    else:
        logger.warning('unhandled nodeType ' + node['nodeType'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url)
    if not next_json:
        return None

    article_json = next_json['pageProps']['data']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['sys']['id']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if article_json.get('writerCredits'):
        item['author']['name'] = re.sub(r'^Skimm\Wd by ', '', article_json['writerCredits'])
    else:
        item['author']['name'] = 'theSkimm'

    item['tags'] = article_json['category'].copy()
    if article_json.get('tags'):
        item['tags'] += article_json['tags'].copy()

    if article_json.get('promoImage'):
        item['_image'] = article_json['promoImage']['img']['url']
    elif article_json.get('headerImage'):
        item['_image'] = article_json['headerImage']['img']['url']

    if article_json.get('featuredDescription'):
        item['summary'] = article_json['featuredDescription']
    elif article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']
    elif article_json.get('socialDescription'):
        item['summary'] = article_json['socialDescription']

    item['content_html'] = ''
    if article_json.get('headerImage'):
        if article_json['headerImage']['__typename'] == 'Image':
            item['content_html'] += add_image(article_json['headerImage'])
        elif article_json['headerImage']['__typename'] == 'Embed':
            if article_json['headerEmbed'].get('src'):
                item['content_html'] += utils.add_embed(article_json['headerEmbed']['src'])

    for content in article_json['body']['json']['content']:
        item['content_html'] += render_content(content, article_json['body']['links'])
    return item


def get_archive(category):
    data = {
        "query": "query Archive($category: String!, $offset: Int!, $limit: Int) {\n  postCollection(order: publish_date_DESC, limit: $limit, skip: $offset, where: {AND: [{OR: [{hideFromArchive_exists: false}, {hideFromArchive: false}]}, {category_contains_some: [$category]}]}) {\n    total\n    items {\n      ...PostPreviewFragment\n    }\n  }\n}\n\nfragment PostPreviewFragment on Post {\n  __typename\n  sys {\n    id\n  }\n  title\n  titlePreview\n  preview\n  featuredDescription\n  sponsoredText\n  headerImage {\n    __typename\n    ... on Image {\n      __typename\n      img {\n        url\n      }\n      alt\n      placeholderData\n    }\n  }\n  promoImage {\n    __typename\n    ... on Image {\n      __typename\n      img {\n        url\n      }\n      alt\n      placeholderData\n    }\n  }\n  slug\n  channelsCollection(limit: 2) {\n    __typename\n    items {\n      ...ChannelFragment\n    }\n  }\n  readTime\n}\n\nfragment ChannelFragment on Channel {\n  __typename\n  title\n  primaryThemeColor\n  slug\n  mappedChannel {\n    __typename\n    title\n    primaryThemeColor\n    slug\n  }\n}\n",
        "variables": {
            "category": category,
            "offset":0,
            "limit":8
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    return utils.post_url(gql_url, json_data=data, headers=headers)


def get_link_button_url(entry_id):
    data = {
        "query": "query LinkButtonQuery($entryId: String!) {\n  linkButton(id: $entryId, preview: false) {\n    ...LinkButtonFragment\n  }\n}\n\nfragment LinkButtonFragment on LinkButton {\n  __typename\n  sys {\n    id\n  }\n  href\n  label\n  buttonStyle\n  image {\n    img {\n      url\n    }\n    credit\n    alt\n  }\n}\n",
        "variables": {
            "entryId": entry_id
        }
    }
    # Bearer auth and gql url in https://www.theskimm.com/_next/static/chunks/pages/_app-005dcc7ff4721468.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "authorization": "Bearer f7e28440632d2f5977f956765e230c018dc84e64f9bb8e720fb58979d44069b2",
        "content-type": "application/json",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    gql_url = 'https://graphql.contentful.com/content/v1/spaces/6g4gfm8wk7b6/environments/master'
    gql_json = utils.post_url(gql_url, json_data=data, headers=headers)
    if not gql_json:
        return ''
    if gql_json['data']['linkButton']['href'].startswith('https'):
        return gql_json['data']['linkButton']['href']
    return 'https://www.theskimm.com' + gql_json['data']['linkButton']['href']


def make_url(post):
    if post['channelsCollection']['items'][0].get('mappedChannel'):
        channel = post['channelsCollection']['items'][0]['mappedChannel']['slug']
    else:
        channel = post['channelsCollection']['items'][0]['slug']
    url = 'https://www.theskimm.com/{}/{}-{}'.format(channel, post['slug'], post['sys']['id'])
    return url


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(args['url'])
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    feed_urls = []
    for component in next_json['pageProps']['referencedComponents']:
        if component['contentType'] == 'archive':
            archive = get_archive(component['componentData']['data']['archive']['category'])
            if archive:
                for it in archive['data']['postCollection']['items']:
                    url = make_url(it)
                    if not url in feed_urls:
                        feed_urls.append(url)
        elif component['contentType'] == 'curatedlist':
            for it in component['componentData']['data']['curatedList']['itemsCollection']['items']:
                url = make_url(it)
                if not url in feed_urls:
                    feed_urls.append(url)
        elif component['contentType'] == 'section':
            for item in component['componentData']['data']['section']['componentsCollection']['items']:
                for it in item['itemsCollection']['items']:
                    if it['__typename'] == 'Post':
                        url = make_url(it)
                        if not url in feed_urls:
                            feed_urls.append(url)
                    else:
                        logger.warning('skipping item type ' + it['__typename'])
        elif component['contentType'] == 'singleitemfeature':
            for link in component['componentData']['data']['singleItemFeature']['featureDescription']['links']['entries']['block']:
                if link['__typename'] == 'LinkButton':
                    url = get_link_button_url(link['sys']['id'])
                    if url and not url in feed_urls:
                        feed_urls.append(url)

    # Remove duplicates

    n = 0
    feed = utils.init_jsonfeed(args)
    feed['title'] = next_json['pageProps']['data']['title']
    feed_items = []
    for url in feed_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def test_handler():
    feeds = ['https://www.theskim.com/',
             'https://www.theskim.com/news',
             'https://www.theskim.com/daily-skimm',
             'https://www.theskim.com/money',
             'https://www.theskim.com/well',
             'https://www.tvguide.com/news/']
    for url in feeds:
        get_feed({"url": url}, True)
