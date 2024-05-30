import json, math, re, uuid
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    gql_url = '{}://{}/graphql'.format(split_url.scheme, split_url.netloc)
    device_id = str(uuid.uuid4())
    gql_data = {
        "operationName": "LookupPathSegmentsQuery",
        "variables": {
            "pathSegments": paths[1:],
            "appInfo": {
                "appId": site_json['app_id'],
                "appVersion": "",
                "preview": False
            },
            "deviceInfo": {
                "deviceId": device_id,
                "deviceModel": "web",
                "locale": "de_DE",
                "smallestScreenWidthDp": 919,
                "deviceOs": "web",
                "platform": "WEB"
            },
            "authorization": {
                "subscriptionCodes":[]
            }
        },
        "query": "query LookupPathSegmentsQuery($appInfo: AppInfo!, $deviceInfo: DeviceInfo!, $authorization: Authorization!, $pathSegments: [String!]!) {\n  catalog(\n    appInfo: $appInfo\n    deviceInfo: $deviceInfo\n    authorization: $authorization\n  ) {\n    lookupPathSegments(pathSegments: $pathSegments) {\n      identifier\n      matches {\n        __typename\n        ... on ContentMatch {\n          id\n          contentType\n          postType\n        }\n        ... on TaxonomyMatch {\n          id\n          identifier\n          parentIdentifier\n          name\n          taxonomyType\n        }\n        ... on CollectionMatch {\n          id\n          name\n        }\n        ... on RedirectMatch {\n          id\n          identifier\n          redirectType\n          target\n          statusCode\n        }\n      }\n    }\n  }\n}"
    }
    gql_json = utils.post_url(gql_url, json_data=gql_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    content_id = ''
    for it in reversed(gql_json['data']['catalog']['lookupPathSegments']):
        for m in it['matches']:
            if m['__typename'] == 'ContentMatch':
                content_id = m['id']
                break
        if content_id:
            break

    if not content_id:
        logger.warning('no content match found for ' + url)
        return None

    gql_data = {
        "operationName": "CatalogContentsQuery",
        "variables": {
            "filter": {
                "id": {
                    "value": content_id
                }
            },
            "first": 1,
            "includeBlocks": True,
            "includeHtml": False,
            "includeResources": True,
            "includeBundledContent": False,
            "includeContentSeoMetadata": False,
            "appInfo": {
                "appId": site_json['app_id'],
                "appVersion": "",
                "preview": False
            },
            "deviceInfo": {
                "deviceId": device_id,
                "deviceModel": "web",
                "locale": "de_DE",
                "smallestScreenWidthDp": 919,
                "deviceOs": "web",
                "platform": "WEB"
            },
            "authorization": {
                "subscriptionCodes":[]
            }
        },
        "query": "query CatalogContentsQuery($appInfo: AppInfo!, $deviceInfo: DeviceInfo!, $authorization: Authorization!, $filter: ContentFilter, $sort: [ContentComparator!], $first: Int, $after: String, $includeBundledContent: Boolean!, $includeResources: Boolean!, $includeBlocks: Boolean!, $includeHtml: Boolean!, $includeContentSeoMetadata: Boolean!, $propertyFilter: PropertyFilter) {\n  catalog(\n    appInfo: $appInfo\n    deviceInfo: $deviceInfo\n    authorization: $authorization\n  ) {\n    contentsConnection(filter: $filter, sort: $sort, first: $first, after: $after) {\n      pageInfo {\n        hasNextPage\n        endCursor\n      }\n      edges {\n        content: node {\n          __typename\n          ...ContentFragment\n          ...PostFragment\n          ...IssueFragment\n          ...BundleFragment\n        }\n      }\n    }\n  }\n}\n\nfragment ContentFragment on Content {\n  __typename\n  id\n  version\n  name\n  description\n  index\n  alias\n  externalId\n  publicationDate\n  unpublishDate\n  lastModified\n  access\n  productId\n  purchaseData {\n    purchased\n    purchasedBy\n  }\n  publication {\n    id\n  }\n  properties(filter: $propertyFilter) {\n    key\n    value\n  }\n  seoMetadata @include(if: $includeContentSeoMetadata) {\n    key\n    value\n  }\n  thumbnails {\n    kind\n    url\n    properties {\n      key\n      value\n    }\n  }\n  categories\n  tags\n}\n\nfragment PostFragment on Post {\n  postType\n  bundleId\n  bundles {\n    id\n    bundleType\n  }\n  taxonomies {\n    ...TaxonomySummaryFragment\n  }\n  authors {\n    name\n    email\n  }\n  bundleId\n  content @include(if: $includeBlocks) {\n    ...ContentBlockFragment\n  }\n  previewContentBlocks @include(if: $includeBlocks) {\n    ...ContentBlockFragment\n  }\n  contentHtml @include(if: $includeHtml)\n  previewContentHtml @include(if: $includeHtml)\n  resources @include(if: $includeResources) {\n    id\n    url\n    type\n    contentLength\n    properties {\n      key\n      value\n      type\n    }\n  }\n}\n\nfragment ContentBlockFragment on ContentBlock {\n  id\n  type\n  parentId\n  children\n  sequence\n  html\n  level\n  properties {\n    key\n    value\n    type\n  }\n}\n\nfragment BundleFragment on Bundle {\n  bundleType\n  taxonomies {\n    ...TaxonomySummaryFragment\n  }\n  authors {\n    name\n    email\n  }\n  contents @include(if: $includeBundledContent) {\n    id\n    content {\n      ...ContentFragment\n      ...PostFragment\n    }\n  }\n}\n\nfragment IssueFragment on Issue {\n  contentLength\n  numberOfPages\n  previewContentLength\n  resources @include(if: $includeResources) {\n    id\n    url\n    type\n    contentLength\n    properties {\n      key\n      value\n      type\n    }\n  }\n}\n\nfragment TaxonomySummaryFragment on Taxonomy {\n  id\n  internalId\n  name\n  type\n  parentId\n  seoMetadata @include(if: $includeContentSeoMetadata) {\n    key\n    value\n  }\n  properties {\n    key\n    value\n  }\n}"
    }
    gql_json = utils.post_url(gql_url, json_data=gql_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    content_json = gql_json['data']['catalog']['contentsConnection']['edges'][0]['content']
    return get_item(content_json, url, args, site_json, save_debug)


def get_item(content_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = content_json['id']
    item['url'] = url
    item['title'] = content_json['name']

    dt = datetime.fromisoformat(content_json['publicationDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('lastModified'):
        dt = datetime.fromisoformat(content_json['lastModified'])
        item['date_modified'] = dt.isoformat()

    authors = []
    item['tags'] = []
    if content_json.get('taxonomies'):
        for it in content_json['taxonomies']:
            if it['type'] == 'author':
                authors.append(it['name'])
            elif it['type'] == 'category':
                item['tags'].append(it['name'])

    if not authors and content_json.get('authors'):
        authors = [it['name'] for it in content_json['authors']]

    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['content_html'] = ''
    if content_json.get('description'):
        item['summary'] = content_json['description']
        item['content_html'] += '<p><em>' + content_json['description'] + '</em></p>'

    if content_json.get('properties'):
        img_src = ''
        caption = ''
        for prop in content_json['properties']:
            if prop['key'] == 'hero_image.url':
                img_src = prop['value']
            elif prop['key'] == 'hero_image.caption' and prop['value'] != 'none':
                caption = prop['value']
        if img_src:
            item['_image'] = img_src
            item['content_html'] += utils.add_image(img_src, caption)

    if not item.get('_image') and content_json.get('thumbnails'):
        item['_image'] = content_json['thumbnails'][0]['url']
        prop = next((it for it in content_json['thumbnails'][0]['properties'] if it['key'] == 'content'), None)
        if prop and prop['value'] != 'none':
            caption = prop['value']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    for block in content_json['content']:
        item['content_html'] += render_content_block(block, content_json['content'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def render_content_block(block, content, is_child=False):
    block_html = ''

    if is_child == False and block.get('parentId'):
        # skip blocks with a parent - process them within the parent
        return block_html
        # parent = next((it for it in content if it['id'] == block['parentId']), None)
        # if parent:
        #     block_html += render_content_block(parent, content)
        #     return block_html
        # else:
        #     logger('unable to find parent block {}'.format(block['parentId']))

    if block['type'] == 'core/paragraph' or block['type'] == 'core/list':
        block_html += block['html']
    elif block['type'] == 'core/heading':
        level = next((it for it in block['properties'] if it['key'] == 'level'), None)
        prop = next((it for it in block['properties'] if it['key'] == 'content'), None)
        if level and prop:
            block_html += '<h{0}>{1}</h{0}>'.format(level['value'], prop['value'])
        else:
            block_html += block['html']
    elif block['type'] == 'core/image':
        img_src = ''
        caption = ''
        link = ''
        for prop in block['properties']:
            if prop['key'] == 'url':
                img_src = prop['value']
            elif prop['key'] == 'content' and prop['value'] != "none":
                caption = prop['value']
            elif prop['key'] == 'linkDestination' and prop['value'] != "none":
                link = prop['value']
        block_html += utils.add_image(img_src, caption, link=link)
    elif block['type'] == 'coblocks/gallery-carousel':
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child:
                block_html += render_content_block(child, content, True)
    elif block['type'] == 'core/video':
        m = re.search(r'<video[^>]+src="([^"]+)"', block['html'])
        if m:
            prop = next((it for it in block['properties'] if it['key'] == 'content'), None)
            if prop and prop['value'] != 'none':
                caption = prop['value']
            else:
                caption = ''
            block_html += utils.add_video(m.group(1), 'video/mp4', None, caption)
        else:
            logger.warning('unhandled core/video content')
    elif block['type'] == 'core/audio':
        m = re.search(r'<audio[^>]+src="([^"]+)"', block['html'])
        if m:
            prop = next((it for it in block['properties'] if it['key'] == 'content'), None)
            if prop and prop['value'] != 'none':
                caption = prop['value']
            else:
                caption = 'Listen'
            block_html += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">{2}</a></span></div><div>&nbsp;</div>'.format(m.group(1), config.server, caption)
        else:
            logger.warning('unhandled core/audio content')
    elif block['type'] == 'core/embed':
        prop = next((it for it in block['properties'] if it['key'] == 'url'), None)
        if prop:
            block_html += utils.add_embed(prop['value'])
        else:
            logger.warning('unhandled core/embed content')
    elif block['type'] == 'core/group':
        block_html += '<div'
        prop = next((it for it in block['properties'] if it['key'] == 'className'), None)
        if prop and prop['value'] != 'none':
            if 'highlight-box' in prop['value']:
                block_html += ' style="background-color:#ccc; padding:12px; border-radius:10px;"'
        block_html += '>'
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child:
                block_html += render_content_block(child, content, True)
        block_html += '</div>'
    elif block['type'] == 'core/columns':
        block_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;'
        prop = next((it for it in block['properties'] if it['key'] == 'className'), None)
        if prop and prop['value'] != 'none':
            if 'highlight-box' in prop['value']:
                block_html += ' background-color:#ccc; padding:12px; border-radius:10px;'
        block_html += '">'
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child and child['type'] == 'core/column':
                block_html += render_content_block(child, content, True)
        block_html += '</div>'
    elif block['type'] == 'core/column':
        block_html += '<div style="flex:1; min-width:256px; margin:auto;">'
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child:
                block_html += render_content_block(child, content, True)
        block_html += '</div>'
    elif block['type'] == 'core/media-text':
        block_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; background-color:#ccc; padding:12px; border-radius:10px;">'
        block_soup = BeautifulSoup(block['html'], 'html.parser')
        el = block_soup.find(class_='wp-block-media-text__media')
        if el:
            block_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(el.img['src'])
        block_html += '<div style="flex:2; min-width:256px; margin:auto;">'
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child:
                block_html += render_content_block(child, content, True)
        block_html += '</div></div>'
    elif block['type'] == 'core/quote':
        prop = next((it for it in block['properties'] if it['key'] == 'quote'), None)
        if prop:
            quote = prop['value']
            prop = next((it for it in block['properties'] if it['key'] == 'author'), None)
            if prop and prop['value'] != 'none':
                caption = prop['value']
            else:
                caption = ''
            block_html += utils.add_pullquote(quote, caption)
        else:
            logger.warning('unhandled core/quote content')
    elif block['type'] == 'core/separator':
        block_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
    elif block['type'] == 'core/buttons':
        for id in block['children']:
            child = next((it for it in content if it['id'] == id), None)
            if child:
                block_html += render_content_block(child, content, True)
    elif block['type'] == 'core/button':
        m = re.search(r'<a[^>]+href="([^"]+)"', block['html'])
        if m:
            prop = next((it for it in block['properties'] if it['key'] == 'content'), None)
            block_html += utils.add_button(m.group(1), prop['value'])
        else:
            logger.warning('unhandled core/button content')
    elif block['type'] == 'acf/button':
        prop = next((it for it in block['properties'] if it['key'] == 'data'), None)
        if prop:
            data = json.loads(prop['value'])
            block_html += utils.add_button(data['buttonPath'], data['buttonText'])
        else:
            logger.warning('unhandled acf/button content')
    elif block['type'] == 'core/html':
        block_soup = BeautifulSoup(block['html'], 'html.parser')
        if block_soup.blockquote and block_soup.blockquote.get('class'):
            if 'instagram-media' in block_soup.blockquote['class']:
                block_html += utils.add_embed(block_soup.blockquote['data-instgrm-permalink'])
        elif block_soup.script and block_soup.script.get('src') and 'jwplayer' in block_soup.script['src']:
            block_html += utils.add_embed(block_soup.script['src'])
        elif block_soup.find(class_='riddle2-wrapper'):
            pass
        else:
            logger.warning('unhandled core/html content')
    elif block['type'] == 'ub/star-rating-block':
        prop = next((it for it in block['properties'] if it['key'] == 'selectedStars'), None)
        if prop:
            n = float(prop['value'])
            block_html += '<div style="font-size:2em; font-weight:bold; color:rgb(255,165,0); margin-bottom:12px;">'
            for i in range(math.floor(n)):
                block_html += '★'
            if n % 1 > 0.0:
                block_html += '½'
            block_html += '</div>'
    elif block['type'] == 'purple/m101-in-text' or block['type'] == 'purple/m101-price-comparsion':
        block_soup = BeautifulSoup(block['html'], 'html.parser')
        el = block_soup.find(class_='m101')
        if el and el.get('data-config'):
            data = json.loads(el['data-config'])
            monetizer_url = 'https://link.monetizer101.com/shop-rest/api/int/shop/918/compare/prices/geolocated/by/accuracy?' + urlencode(data) + '&filter-merchant=&xp=1&&url=' + quote_plus(el['data-url'])
            if not data.get('limit'):
                monetizer_url += '&limit=3'
            monetizer_json = utils.get_url_json(monetizer_url)
            if monetizer_json:
                caption = 'Buy at {} ({}{:.2f})'.format(monetizer_json[0]['merchant']['name'], '$' if monetizer_json[0]['currency'] == 'USD' else '€', float(monetizer_json[0]['salePrice']))
                block_html += utils.add_button(utils.get_redirect_url(monetizer_json[0]['deepLink']), caption)
    # elif block['type'] == 'core/buttons' or block['type'] == 'purple/m101-price-comparsion':
    #     prop = next((it for it in block['properties'] if it['key'] == 'content'), None)
    #     if not prop or prop['value'] != '':
    #         logger.warning('unhandled content block type ' + block['type'])
    else:
        logger.warning('unhandled content block type ' + block['type'])
    return block_html


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) != 1:
        logger.warning('unhandled feed url ' + url)
        return None

    gql_url = '{}://{}/graphql'.format(split_url.scheme, split_url.netloc)
    device_id = str(uuid.uuid4())
    gql_data = {
        "operationName": "CatalogContentsQuery",
        "variables": {
            "filter": {
                "AND": [
                    {
                        "taxonomies": {
                            "content": {
                                "value": {
                                    "AND": [
                                        {
                                            "id": {
                                                "value": paths[0]
                                            }
                                        },
                                        {
                                            "type": {
                                                "value": "category"
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    {
                        "properties": {
                            "key": "sponsor_type",
                            "value": "native-true",
                            "negated": True
                        }
                    },
                    {
                        "properties": {
                            "key": "sponsor_type",
                            "value": "native-advertorial",
                            "negated": True
                        }
                    }
                ]
            },
            "sort": [
                {
                    "publicationDate": {
                        "direction": "DESC"
                    }
                }
            ],
            "first": 10,
            "includeBlocks": True,
            "includeHtml": False,
            "includeResources": False,
            "includeBundledContent": False,
            "includeContentSeoMetadata": False,
            "appInfo": {
                "appId": site_json['app_id'],
                "appVersion": "",
                "preview": False
            },
            "deviceInfo": {
                "deviceId": device_id,
                "deviceModel": "web",
                "locale": "de_DE",
                "smallestScreenWidthDp": 919,
                "deviceOs": "web",
                "platform": "WEB"
            },
            "authorization": {
                "subscriptionCodes":[]
            }
        },
        "query":"query CatalogContentsQuery($appInfo: AppInfo!, $deviceInfo: DeviceInfo!, $authorization: Authorization!, $filter: ContentFilter, $sort: [ContentComparator!], $first: Int, $after: String, $includeBundledContent: Boolean!, $includeResources: Boolean!, $includeBlocks: Boolean!, $includeHtml: Boolean!, $includeContentSeoMetadata: Boolean!, $propertyFilter: PropertyFilter) {\n  catalog(\n    appInfo: $appInfo\n    deviceInfo: $deviceInfo\n    authorization: $authorization\n  ) {\n    contentsConnection(filter: $filter, sort: $sort, first: $first, after: $after) {\n      pageInfo {\n        hasNextPage\n        endCursor\n      }\n      edges {\n        content: node {\n          __typename\n          ...ContentFragment\n          ...PostFragment\n          ...IssueFragment\n          ...BundleFragment\n        }\n      }\n    }\n  }\n}\n\nfragment ContentFragment on Content {\n  __typename\n  id\n  version\n  name\n  description\n  index\n  alias\n  externalId\n  publicationDate\n  unpublishDate\n  lastModified\n  access\n  productId\n  purchaseData {\n    purchased\n    purchasedBy\n  }\n  publication {\n    id\n  }\n  properties(filter: $propertyFilter) {\n    key\n    value\n  }\n  seoMetadata @include(if: $includeContentSeoMetadata) {\n    key\n    value\n  }\n  thumbnails {\n    kind\n    url\n    properties {\n      key\n      value\n    }\n  }\n  categories\n  tags\n}\n\nfragment PostFragment on Post {\n  postType\n  bundleId\n  bundles {\n    id\n    bundleType\n  }\n  taxonomies {\n    ...TaxonomySummaryFragment\n  }\n  authors {\n    name\n    email\n  }\n  bundleId\n  content @include(if: $includeBlocks) {\n    ...ContentBlockFragment\n  }\n  previewContentBlocks @include(if: $includeBlocks) {\n    ...ContentBlockFragment\n  }\n  contentHtml @include(if: $includeHtml)\n  previewContentHtml @include(if: $includeHtml)\n  resources @include(if: $includeResources) {\n    id\n    url\n    type\n    contentLength\n    properties {\n      key\n      value\n      type\n    }\n  }\n}\n\nfragment ContentBlockFragment on ContentBlock {\n  id\n  type\n  parentId\n  children\n  sequence\n  html\n  level\n  properties {\n    key\n    value\n    type\n  }\n}\n\nfragment BundleFragment on Bundle {\n  bundleType\n  taxonomies {\n    ...TaxonomySummaryFragment\n  }\n  authors {\n    name\n    email\n  }\n  contents @include(if: $includeBundledContent) {\n    id\n    content {\n      ...ContentFragment\n      ...PostFragment\n    }\n  }\n}\n\nfragment IssueFragment on Issue {\n  contentLength\n  numberOfPages\n  previewContentLength\n  resources @include(if: $includeResources) {\n    id\n    url\n    type\n    contentLength\n    properties {\n      key\n      value\n      type\n    }\n  }\n}\n\nfragment TaxonomySummaryFragment on Taxonomy {\n  id\n  internalId\n  name\n  type\n  parentId\n  seoMetadata @include(if: $includeContentSeoMetadata) {\n    key\n    value\n  }\n  properties {\n    key\n    value\n  }\n}"
    }
    gql_json = utils.post_url(gql_url, json_data=gql_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for edge in gql_json['data']['catalog']['contentsConnection']['edges']:
        content = edge['content']
        content_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
        if content.get('properties'):
            prop = next((it for it in content['properties'] if it['key'] == 'taxonomy.category.primary'), None)
            if prop:
                content_url += '/' + prop['value']
            prop = next((it for it in content['properties'] if it['key'] == 'slug'), None)
            if prop:
                content_url += '/' + prop['value']
        if save_debug:
            logger.debug('getting content for ' + content_url)
        item = get_item(content, content_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # if api_json['seo'].get('metaTitle'):
    #     feed['title'] = api_json['seo']['metaTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
