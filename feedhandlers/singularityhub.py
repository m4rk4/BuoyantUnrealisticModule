import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        query = ''
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
        query = '?path=' + '&path='.join(paths)
    next_url = '{}://{}/_next/data/{}{}.json{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    # print(next_url)
    next_data = utils.get_url_json(next_url)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                logger.debug('updating {} buildId'.format(split_url.netloc))
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            return next_data['props']
    return next_data


def format_block(block):
    block_html = ''
    if block['name'] == 'core/paragraph':
        attr_json = json.loads(block['attributesJSON'])
        if attr_json['content'].startswith('<script'):
            return block_html
        elif attr_json['content'].startswith('<iframe'):
            m = re.search(r'src="([^"]+)"', attr_json['content'])
            block_html += utils.add_embed(m.group(1))
        else:
            # TODO: check attr_json['dropCap'] == True
            block_html += block['originalContent']
    elif block['name'] == 'core/heading':
        attr_json = json.loads(block['attributesJSON'])
        block_html += '<h{0}>{1}</h{0}>'.format(attr_json['level'], attr_json['content'])
    elif block['name'] == 'core/image':
        attr_json = json.loads(block['attributesJSON'])
        block_html += utils.add_image(attr_json['url'], attr_json['caption'])
    elif block['name'] == 'core/list':
        attr_json = json.loads(block['attributesJSON'])
        if attr_json['ordered'] == True:
            tag = 'ol'
        else:
            tag = 'ul'
        block_html += '<{}>'.format(tag)
        for blk in block['innerBlocks']:
            block_html += format_block(blk)
        block_html += '</{}>'.format(tag)
    elif block['name'] == 'core/list-item':
        attr_json = json.loads(blk['attributesJSON'])
        block_html += '<li style="margin:4px 0 4px 0;">' + attr_json['content'] + '</li>'
    elif block['name'] == 'core/embed':
        attr_json = json.loads(block['attributesJSON'])
        block_html += utils.add_embed(attr_json['url'])
    elif block['name'] == 'core/freeform':
        if block['attributesJSON'] != '[]':
            logger.warning('unhandled core/freeform block')
    elif block['name'] == 'core/quote':
        attr_json = json.loads(block['innerBlocks'][-1]['attributesJSON'])
        m = re.search(r'href="(https://twitter\.com/[^/]+/status/\d+)', attr_json['content'])
        if m:
            block_html += utils.add_embed(m.group(1))
        else:
            content_html = ''
            for blk in block['innerBlocks']:
                content_html += format_block(blk)
            # TODO: blockquote or pullquote
            block_html += utils.add_blockquote(content_html)
    elif block['name'] == 'core/separator':
        block_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
    elif block['name'] == 'core/html':
        soup = BeautifulSoup(block['originalContent'], 'html.parser')
        el = soup.find('iframe')
        if el:
            block_html += utils.add_embed(el['src'])
        else:
            logger.warning('unhandled core/html block')
    elif block['name'] == 'core/post-excerpt':
        pass
    else:
        logger.warning('unhandled {} block'.format(block['name']))
    return block_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    post_json = None
    split_url = urlsplit(url)
    for query in next_data['pageProps']['dehydratedState']['queries']:
        if split_url.path in query['queryHash']:
            post_json = query['state']['data']['resolveUrl']['node']
            break
    if not post_json:
        logger.warning('unable to find post query in ' + url)
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['databaseId']
    item['url'] = 'https://' + urlsplit(url).netloc + post_json['uri']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['seo']['opengraphPublishedTime']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)
    if post_json['seo'].get('opengraphModifiedTime'):
        dt = datetime.fromisoformat(post_json['seo']['opengraphModifiedTime']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in post_json['authorTags']['nodes']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if post_json['categories'].get('nodes'):
        item['tags'] += [x['name'] for x in post_json['categories']['nodes']]
    if post_json['tags'].get('nodes'):
        item['tags'] += [x['name'] for x in post_json['tags']['nodes']]
    if len(item['tags']) == 0:
        del item['tags']

    item['image'] = post_json['seo']['opengraphImage']['sourceUrl']
    item['summary'] = post_json['seo']['opengraphDescription']

    item['content_html'] = ''
    if post_json.get('excerpt'):
        item['content_html'] += '<p><em>' + post_json['excerpt'] + '</em></p>'

    if post_json['featuredVideo'].get('id'):
        logger.warning('unhandled featuredVideo in ' + url)
    elif post_json['featuredImage'].get('node'):
        captions = []
        if post_json['featuredImage']['node'].get('caption'):
            captions.append(post_json['featuredImage']['node']['caption'])
        if post_json['featuredImage']['node']['mediaAdditionalData']['mediaCredit'].get('mcName'):
            captions.append(post_json['featuredImage']['node']['mediaAdditionalData']['mediaCredit']['mcName'])
        item['content_html'] += utils.add_image(post_json['featuredImage']['node']['sourceUrl'], ' | '.join(captions))

    for block in post_json['blocks']:
        item['content_html'] += format_block(block)

    if 'Curation' in item['tags']:
        soup = BeautifulSoup(item['content_html'], 'html.parser')
        for el in soup.select('p:has(> a > strong)'):
            new_el = BeautifulSoup(utils.add_embed(el.a['href']), 'html.parser')
            el.insert_after(new_el)
        item['content_html'] = str(soup)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    posts = None
    gql_data = None
    if len(paths) == 0:
        gql_data = {
            "query": "\n  query LatestPosts(\n    $excludeCategory: [ID]\n    $first: Int\n    $last: Int\n    $before: String\n    $after: String\n    $orderField: PostObjectsConnectionOrderbyEnum!\n    $order: OrderEnum!\n  ) {\n    posts(\n      where: {\n        categoryNotIn: $excludeCategory\n        syndicationWeb: true\n        orderby: { field: $orderField, order: $order }\n      }\n      first: $first\n      last: $last\n      before: $before\n      after: $after\n    ) {\n      pageInfo {\n        ...PagePaginationInfoFragment\n      }\n      nodes {\n        ...PostFragment\n      }\n    }\n  }\n  \n  fragment PostFragment on Post {\n    id\n    databaseId\n    authorTags {\n      nodes {\n        name\n        uri\n        count\n      }\n    }\n    categories(where: { orderby: TERM_ORDER }) {\n      nodes {\n        ...CategoryLinkFragment\n      }\n    }\n    primaryCategory {\n      ...CategoryLinkFragment\n    }\n    excerpt\n    featuredImageAltText\n    featuredImageUrl\n    featuredImageListUrl\n    featuredImage {\n      node {\n        ...MediaFragment\n      }\n    }\n    featuredImageVertical {\n      featuredImageVertical {\n        ...MediaFragment\n      }\n    }\n    date\n    modified\n    showModifiedDate\n    uri\n    title\n    tags(first: 25) {\n      nodes {\n        name\n        uri\n        slug\n      }\n    }\n    slug\n  }\n  \n  fragment PagePaginationInfoFragment on WPPageInfo {\n    hasNextPage\n    hasPreviousPage\n    startCursor\n    endCursor\n  }\n\n  fragment CategoryLinkFragment on Category {\n    uri\n    name\n    slug\n    databaseId\n    parentDatabaseId\n  }\n\n  fragment MediaFragment on MediaItem {\n    altText\n    caption\n    cropPosition\n    id\n    sourceUrl\n    title\n    mediaDetails {\n      height\n      width\n    }\n    mediaAdditionalData {\n      mediaSubtitle\n      mediaCredit {\n        mcName\n      }\n    }\n  }\n",
            "variables": {
                "excludeCategory": [],
                "first": 10,
                "last": 0,
                "before": "",
                "after": "",
                "orderField": "DATE",
                "order": "DESC"
            }
        }
    elif 'category' in paths:
        gql_data = {
            "query": "\n  query GetPostsByTag(\n    $categoryName: String\n    $offset: Int = 10\n    $size: Int = 10\n  ) {\n    posts(\n      where: {\n        categoryName: $categoryName\n        offsetPagination: { offset: $offset, size: $size }\n      }\n    ) {\n      nodes {\n        id\n        title\n        uri\n        excerpt\n        categories {\n          nodes {\n            name\n            uri\n            databaseId\n          }\n        }\n        date\n        featuredImage {\n          node {\n            altText\n            sourceUrl\n          }\n        }\n        authorTags {\n          nodes {\n            name\n            uri\n          }\n        }\n      }\n    }\n  }\n",
            "variables": {
                "categoryName": paths[1],
                "offset": 0,
                "size": 10
            }
        }
    elif 'tag' in paths:
        gql_data = {
            "query": "\n  query GetPostsByTag(\n    $tagSlugIn: [String]\n    $offset: Int = 10\n    $size: Int = 10\n  ) {\n    posts(\n      where: {\n        tagSlugIn: $tagSlugIn\n        offsetPagination: { offset: $offset, size: $size }\n      }\n    ) {\n      nodes {\n        id\n        title\n        uri\n        excerpt\n        categories {\n          nodes {\n            name\n            uri\n            databaseId\n          }\n        }\n        date\n        featuredImage {\n          node {\n            altText\n            sourceUrl\n          }\n        }\n        authorTags {\n          nodes {\n            name\n            uri\n          }\n        }\n      }\n    }\n  }\n",
            "variables": {
                "tagSlugIn": paths[1],
                "offset": 0,
                "size": 10
            }
        }
    elif 'author' in paths:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/next.json')
        for query in next_data['pageProps']['dehydratedState']['queries']:
            if split_url.path in query['queryHash']:
                posts = query['state']['data']['resolveUrl']['node']['posts']['nodes']
                break
        
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    if gql_data:
        gql_json = utils.post_url('https://cms.singularityhub.com/wp/graphql', json_data=gql_data)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        posts = gql_json['data']['posts']['nodes']

    if not posts:
        logger.warning('unable to get posts for ' + url)
        return None

    n = 0
    feed_items = []
    for post in posts:
        post_url = 'https://' + split_url.netloc + post['uri']
        if save_debug:
            logger.debug('getting content from ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
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
