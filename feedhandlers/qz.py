import hashlib, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    return 'https://i.kinja-img.com/gawker-media/image/upload/c_fill,f_auto,fl_progressive,g_center,pg_1,q_80,w_{}/{}'.format(width, paths[-1])


def get_graphql_query(gql_query, persisted=True):
    variables = json.dumps(gql_query['variables']).replace(' ', '').replace('"NULL"', 'null')
    if persisted:
        query_hash = hashlib.sha256(bytes(gql_query['query'], 'ascii')).hexdigest()
        gql_url = 'https://content-gql-proxy.qz.com/graphql?operationName={}&variables={}&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22{}%22%7D%7D'.format(gql_query['operationName'], quote(variables), query_hash)
    else:
        gql_url = 'https://content-gql-proxy.qz.com/graphql?operationName={}&variables={}&query={}'.format(gql_query['operationName'], quote(variables), quote(gql_query['query']))

    print(gql_url)
    #print(query_hash)
    gql_json = utils.get_url_json(gql_url)
    return gql_json


def get_email_by_id(email_id):
    gql_query = {
        "operationName": "EmailById",
        "variables": {"id": int(email_id)},
        "query": "\n    query EmailById($id: Int!, $previewTime: Int, $previewToken: String) {\n  emails(where: {id: $id, preview: {time: $previewTime, token: $previewToken}}) {\n    nodes {\n      ...EmailParts\n      html\n      emailLists {\n        nodes {\n          ...EmailListParts\n        }\n      }\n    }\n  }\n}\n    \n    fragment EmailParts on Email {\n  ...EmailTeaserParts\n  disablePaywall\n  blocks {\n    ...BlockParts\n    connections {\n      __typename\n      ... on Promotion {\n        ...PromotionParts\n      }\n    }\n  }\n  sendgridID\n  emailLogoAd {\n    alt\n    src\n    url\n  }\n}\n    \n\n    fragment EmailTeaserParts on Email {\n  id\n  dateGmt\n  emailId\n  featuredImage {\n    ...MediaParts\n  }\n  link\n  slug\n  segment\n  socialImage {\n    ...MediaParts\n  }\n  seoTitle\n  socialDescription\n  socialTitle\n  subject\n  title\n  authors: coAuthors {\n    nodes {\n      ...AuthorParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment AuthorParts on CoAuthor {\n  avatar\n  bio\n  emeritus\n  email\n  facebook\n  firstName\n  id\n  instagram\n  lastName\n  linkedin\n  name\n  organization\n  pgp\n  shortBio\n  title\n  twitter\n  type\n  url\n  username\n  website\n}\n    \n\n    fragment BlockParts on Block {\n  attributes {\n    name\n    value\n  }\n  id\n  innerHtml\n  tagName\n  type\n}\n    \n\n    fragment PromotionParts on Promotion {\n  content\n  dateGmt\n  description: excerpt\n  destination\n  featuredImage {\n    ...MediaParts\n  }\n  id\n  link\n  modified\n  title\n}\n    \n\n    fragment EmailListParts on EmailList {\n  id\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  isPrivate: private\n  link\n  listId\n  name\n  slug\n  colors\n  summary\n  subtitle\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_article(article_id):
    gql_query = {
        "operationName": "Article",
        "variables": {"id": int(article_id)},
        "query": "\n    query Article($id: Int!, $previewTime: Int, $previewToken: String) {\n  posts(where: {id: $id, preview: {time: $previewTime, token: $previewToken}}) {\n    nodes {\n      ...ArticleParts\n    }\n  }\n}\n    \n    fragment ArticleParts on Post {\n  ...ArticleTeaserParts\n  authors: coAuthors {\n    nodes {\n      ...AuthorParts\n    }\n  }\n  blocks {\n    ...BlockParts\n  }\n  brandSafety\n  canonicalUrl\n  colorScheme\n  contentType {\n    node {\n      name\n    }\n  }\n  excerpt\n  featuredImageSize\n  flags {\n    nodes {\n      name\n      slug\n    }\n  }\n  footnotes\n  guides {\n    nodes {\n      ...GuideParts\n    }\n  }\n  interactiveSource\n  interactiveShowHeader\n  locations {\n    nodes {\n      name\n    }\n  }\n  metered\n  modifiedGmt\n  obsessions {\n    nodes {\n      ...ObsessionParts\n    }\n  }\n  paywalled\n  projects {\n    nodes {\n      ...ProjectParts\n    }\n  }\n  readNext\n  serieses {\n    nodes {\n      ...SeriesParts\n    }\n  }\n  shows {\n    nodes {\n      ...ShowParts\n    }\n  }\n  slug\n  seoTitle\n  socialDescription\n  socialImage\n  socialTitle\n  subtype\n  suppressAds\n  tags(where: {orderby: COUNT}, last: 20) {\n    nodes {\n      id\n      name\n      slug\n    }\n  }\n  topics {\n    nodes {\n      id\n      name\n      slug\n    }\n  }\n  trackingUrls\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    \n\n    fragment AuthorParts on CoAuthor {\n  avatar\n  bio\n  emeritus\n  email\n  facebook\n  firstName\n  id\n  instagram\n  lastName\n  linkedin\n  name\n  organization\n  pgp\n  shortBio\n  title\n  twitter\n  type\n  url\n  username\n  website\n}\n    \n\n    fragment BlockParts on Block {\n  attributes {\n    name\n    value\n  }\n  id\n  innerHtml\n  tagName\n  type\n}\n    \n\n    fragment GuideParts on Guide {\n  id\n  guideId\n  hasEssentials\n  link\n  count\n  description\n  shortDescription\n  name\n  slug\n  featuredImage {\n    ...MediaParts\n  }\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n  colors\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n}\n    \n\n    fragment ObsessionParts on Obsession {\n  id\n  description\n  hasEssentials\n  headerImage {\n    ...MediaParts\n  }\n  link\n  name\n  shortDescription\n  slug\n  subtitle\n  featuredImage {\n    ...MediaParts\n  }\n  sponsor {\n    name\n    campaign {\n      id\n      logo\n      logoLink\n    }\n  }\n}\n    \n\n    fragment ProjectParts on Project {\n  id\n  count\n  description\n  shortDescription\n  link\n  name\n  slug\n}\n    \n\n    fragment SeriesParts on Series {\n  colors\n  count\n  description\n  emailListId\n  ended\n  featuredImage {\n    ...MediaParts\n  }\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n  headerVideos {\n    size\n    mp4 {\n      ...MediaParts\n    }\n    webm {\n      ...MediaParts\n    }\n    poster {\n      ...MediaParts\n    }\n  }\n  id\n  link\n  name\n  postOrder\n  shortDescription\n  showToc\n  slug\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n}\n    \n\n    fragment ShowParts on Show {\n  colors\n  count\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n  headerVideos {\n    size\n    mp4 {\n      ...MediaParts\n    }\n    webm {\n      ...MediaParts\n    }\n    poster {\n      ...MediaParts\n    }\n  }\n  id\n  link\n  name\n  postOrder\n  shortDescription\n  slug\n  socialImage {\n    ...MediaParts\n  }\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_item(post_json, args, save_debug=False):
    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('modifiedGmt'):
        dt = datetime.fromisoformat(post_json['modifiedGmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    if post_json.get('authors') and post_json['authors'].get('nodes'):
        for it in post_json['authors']['nodes']:
            authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if post_json.get('tags') and post_json['tags'].get('nodes'):
        for it in post_json['tags']['nodes']:
            item['tags'].append(it['name'])
    if post_json.get('topics') and post_json['topics'].get('nodes'):
        for it in post_json['topics']['nodes']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''

    if post_json.get('video') and post_json['video']['type'] == 'vimeo':
        item['content_html'] += utils.add_embed('https://player.vimeo.com/video/' + post_json['video']['id'])
    elif post_json.get('featuredImage'):
        item['_image'] = post_json['featuredImage']['sourceUrl']
        if post_json['blocks'][0]['type'] != 'SHORTCODE_CAPTION':
            captions = []
            if post_json['featuredImage'].get('caption'):
                captions.append(post_json['featuredImage']['caption'])
            if post_json['featuredImage'].get('credit'):
                captions.append(post_json['featuredImage']['credit'])
            item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))
    elif post_json.get('socialImage'):
        item['_image'] = resize_image(post_json['socialImage'])

    if post_json.get('blocks'):
        for block in post_json['blocks']:
            if re.search(r'^(P|H\d|OL|UL|TABLE)$', block['type']):
                item['content_html'] += '<{0}>{1}</{0}>'.format(block['tagName'], block['innerHtml'])

            elif block['type'] == 'HR':
                item['content_html'] += '<hr/>'

            elif block['type'] == 'PRE':
                item['content_html'] += '<pre style="white-space: pre-wrap;">{}</pre>'.format(block['innerHtml'])

            elif block['type'] == 'EL':
                bullet = next((it for it in block['attributes'] if it['name'] == 'emojiBullets'), None)
                if bullet:
                    inner_html = re.sub(r'<li\b\s?[^>]*>', '<li>{} '.format(bullet['value']), block['innerHtml'])
                    item['content_html'] += '<ul style="list-style-type: none;">{}</ul>'.format(inner_html)
                else:
                    logger.warning('unhandled EL list in ' + item['url'])
                    item['content_html'] += '<ul>{}</ul>'.format(block['innerHtml'])

            elif block['type'] == 'BLOCKQUOTE':
                item['content_html'] += utils.add_blockquote(block['innerHtml'])

            elif block['type'] == 'SHORTCODE_PULLQUOTE':
                item['content_html'] += utils.add_pullquote(block['innerHtml'])

            elif block['type'] == 'SHORTCODE_CAPTION':
                img_src = next((it for it in block['attributes'] if it['name'] == 'url'), None)
                captions = []
                caption = next((it for it in block['attributes'] if it['name'] == 'caption'), None)
                if caption and caption['value']:
                    captions.append(caption['value'])
                caption = next((it for it in block['attributes'] if it['name'] == 'credit'), None)
                if caption and caption['value']:
                    captions.append(caption['value'])
                if img_src:
                    item['content_html'] += utils.add_image(resize_image(img_src['value']), ' | '.join(captions))
                else:
                    logger.warning('unhandled SHORTCODE_CAPTION block in ' + item['url'])

            elif block['type'] == 'IMG':
                img_src = next((it for it in block['attributes'] if it['name'] == 'src'), None)
                # If it's a 1x1 img, skip it
                width = next((it for it in block['attributes'] if it['name'] == 'width'), None)
                height = next((it for it in block['attributes'] if it['name'] == 'height'), None)
                if (width and height) and (int(width['value']) > 1 and int(height['value']) > 1):
                    item['content_html'] += utils.add_image(resize_image(img_src['value']))

            elif block['type'] == 'SHORTCODE_VIDEO':
                video = next((it for it in block['attributes'] if it['name'] == 'mp4'), None)
                if video:
                    poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(video['value']))
                    item['content_html'] += utils.add_video(video['value'], 'video/mp4', poster)

            elif block['type'].startswith('EMBED_'):
                embed_url = next((it for it in block['attributes'] if it['name'] == 'url'), None)
                if embed_url:
                    item['content_html'] += utils.add_embed(embed_url['value'])
                else:
                    logger.warning('unhandled block {} in {}'.format(block['type'], item['url']))

            elif block['type'] == 'SHORTCODE_BUTTON':
                href = next((it for it in block['attributes'] if it['name'] == 'href'), None)
                if not (href and href['value'] == 'https://qz.com/become-a-member'):
                    logger.warning('unhandled SHORTCODE_BUTTON in ' + item['url'])

            elif re.search(r'_PARTNER|_REFERRAL|_SPONSOR', block['type']):
                continue

            else:
                logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))

    item['content_html'] = item['content_html'].replace('<hr/><hr/>', '<hr/>')
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    post_json = None
    if paths[0] == 'emails':
        gql_json = get_email_by_id(paths[2])
        if gql_json:
            post_json = gql_json['data']['emails']['nodes'][0]
    else:
        m = re.search(r'-(\d+)$', split_url.path)
        if m:
            gql_json = get_article(m.group(1))
        else:
            if paths[-2].isnumeric():
                gql_json = get_article(paths[-2])
            else:
                logger.warning('unable to determine article id in ' + url)
                return None
        if gql_json:
            post_json = gql_json['data']['posts']['nodes'][0]

    if not post_json:
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')
    return get_item(post_json, args, save_debug)


def get_emails_by_tag(slug_list):
    gql_query = {
        "operationName":"EmailsByTag",
        "variables": {"perPage": 10, "slug": slug_list},
        "query": "\n    query EmailsByTag($after: String = \"\", $perPage: Int = 10, $slug: [String]) {\n  emails(after: $after, first: $perPage, where: {tagSlugIn: $slug}) {\n    nodes {\n      ...EmailTeaserParts\n      link\n      emailLists {\n        nodes {\n          ...EmailListParts\n        }\n      }\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n}\n    \n    fragment EmailTeaserParts on Email {\n  id\n  dateGmt\n  emailId\n  featuredImage {\n    ...MediaParts\n  }\n  link\n  slug\n  segment\n  socialImage {\n    ...MediaParts\n  }\n  seoTitle\n  socialDescription\n  socialTitle\n  subject\n  title\n  authors: coAuthors {\n    nodes {\n      ...AuthorParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment AuthorParts on CoAuthor {\n  avatar\n  bio\n  emeritus\n  email\n  facebook\n  firstName\n  id\n  instagram\n  lastName\n  linkedin\n  name\n  organization\n  pgp\n  shortBio\n  title\n  twitter\n  type\n  url\n  username\n  website\n}\n    \n\n    fragment EmailListParts on EmailList {\n  id\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  isPrivate: private\n  link\n  listId\n  name\n  slug\n  colors\n  summary\n  subtitle\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_emails_by_list(slug):
    gql_query = {
        "operationName":"EmailsByList",
        "variables": {"perPage": 10, "slug": slug, "tags": []},
        "query": "\n    query EmailsByList($after: String = \"\", $perPage: Int = 10, $slug: [String]!, $tags: [String]) {\n  emailLists(where: {slug: $slug}) {\n    nodes {\n      ...EmailListParts\n      emails(after: $after, first: $perPage, where: {tagSlugIn: $tags}) {\n        nodes {\n          ...EmailTeaserParts\n        }\n        pageInfo {\n          endCursor\n          hasNextPage\n        }\n      }\n    }\n  }\n}\n    \n    fragment EmailListParts on EmailList {\n  id\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  isPrivate: private\n  link\n  listId\n  name\n  slug\n  colors\n  summary\n  subtitle\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment EmailTeaserParts on Email {\n  id\n  dateGmt\n  emailId\n  featuredImage {\n    ...MediaParts\n  }\n  link\n  slug\n  segment\n  socialImage {\n    ...MediaParts\n  }\n  seoTitle\n  socialDescription\n  socialTitle\n  subject\n  title\n  authors: coAuthors {\n    nodes {\n      ...AuthorParts\n    }\n  }\n}\n    \n\n    fragment AuthorParts on CoAuthor {\n  avatar\n  bio\n  emeritus\n  email\n  facebook\n  firstName\n  id\n  instagram\n  lastName\n  linkedin\n  name\n  organization\n  pgp\n  shortBio\n  title\n  twitter\n  type\n  url\n  username\n  website\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_obsessions():
    gql_query = {
        "operationName": "Obsessions",
        "variables": {"postsPerPage": 3, "perPage": 25, "location": "OBSESSIONS_QUARTZ"},
        "query": "\n    query Obsessions($perPage: Int!, $postsPerPage: Int = 1, $location: MenuLocationEnum!) {\n  menuItems(first: $perPage, where: {location: $location}) {\n    nodes {\n      id\n      connectedObject {\n        __typename\n        ... on Obsession {\n          ...ObsessionParts\n          posts(first: $postsPerPage) {\n            nodes {\n              ...ArticleTeaserParts\n            }\n          }\n        }\n      }\n    }\n  }\n}\n    \n    fragment ObsessionParts on Obsession {\n  id\n  description\n  hasEssentials\n  headerImage {\n    ...MediaParts\n  }\n  link\n  name\n  shortDescription\n  slug\n  subtitle\n  featuredImage {\n    ...MediaParts\n  }\n  sponsor {\n    name\n    campaign {\n      id\n      logo\n      logoLink\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "}
    return get_graphql_query(gql_query)


def get_latest_articles(edition):
    gql_query = {
        "operationName": "LatestArticles",
        "variables": {"after": "", "edition": edition.upper(), "perPage": 10},
        "query": "\n    query LatestArticles($after: String = \"\", $edition: EditionName, $perPage: Int) {\n  posts(after: $after, first: $perPage, where: {edition: $edition}) {\n    nodes {\n      ...ArticleTeaserParts\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n}\n    \n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "}
    return get_graphql_query(gql_query)


def get_articles_by_id(article_ids):
    gql_query = {
        "operationName": "ArticlesByIds",
        "variables": {"after": "", "ids": article_ids, "postsPerPage": 20},
        "query": "\n    query ArticlesByIds($ids: [ID!], $postsPerPage: Int!, $after: String = \"\") {\n  posts(where: {in: $ids}, first: $postsPerPage, after: $after) {\n    nodes {\n      ...ArticleTeaserParts\n    }\n  }\n}\n    \n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_articles_by_topic(slug_list):
    gql_query = {
        "operationName": "ArticlesByTopic",
        "variables": {"perPage": 10, "slug": slug_list},
        "query": "\n    query ArticlesByTopic($after: String = \"\", $perPage: Int, $slug: [String]) {\n  topics(where: {slug: $slug}) {\n    nodes {\n      ...TopicParts\n      posts(after: $after, first: $perPage) {\n        nodes {\n          ...ArticleTeaserParts\n        }\n        pageInfo {\n          endCursor\n          hasNextPage\n        }\n      }\n    }\n  }\n}\n    \n    fragment TopicParts on Topic {\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  id\n  link\n  name\n  shortDescription\n  slug\n  topicId\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "}
    return get_graphql_query(gql_query)


def get_articles_by_guide(slug_list):
    gql_query = {
        "operationName": "ArticlesByGuide",
        "variables": {"after": "", "perPage": 10, "slug": slug_list},
        "query": "\n    query ArticlesByGuide($after: String = \"\", $perPage: Int, $slug: [String]) {\n  guides(last: 1, where: {slug: $slug}) {\n    nodes {\n      ...GuideParts\n      posts(\n        after: $after\n        first: $perPage\n        where: {orderby: {field: DATE, order: ASC}}\n      ) {\n        nodes {\n          ...ArticleTeaserParts\n        }\n        pageInfo {\n          hasNextPage\n          endCursor\n        }\n      }\n    }\n  }\n}\n    \n    fragment GuideParts on Guide {\n  id\n  guideId\n  hasEssentials\n  link\n  count\n  description\n  shortDescription\n  name\n  slug\n  featuredImage {\n    ...MediaParts\n  }\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n  colors\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_articles_by_series(slug_list):
    gql_query = {
        "operationName": "ArticlesBySeries",
        "variables": {"perPage": 10, "slug": slug_list},
        "query": "\n    query ArticlesBySeries($after: String = \"\", $perPage: Int, $slug: [String]) {\n  serieses(where: {slug: $slug}) {\n    nodes {\n      ...SeriesParts\n      posts(after: $after, first: $perPage) {\n        nodes {\n          ...ArticleTeaserParts\n        }\n        pageInfo {\n          endCursor\n          hasNextPage\n        }\n      }\n    }\n  }\n}\n    \n    fragment SeriesParts on Series {\n  colors\n  count\n  description\n  emailListId\n  ended\n  featuredImage {\n    ...MediaParts\n  }\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n  headerVideos {\n    size\n    mp4 {\n      ...MediaParts\n    }\n    webm {\n      ...MediaParts\n    }\n    poster {\n      ...MediaParts\n    }\n  }\n  id\n  link\n  name\n  postOrder\n  shortDescription\n  showToc\n  slug\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "}
    return get_graphql_query(gql_query)


def get_content_by_author(slug):
    gql_query = {
        "operationName": "ContentByAuthor",
        "variables": {"perPage": 10, "slug": slug, "after": ""},
        "query":"\n    query ContentByAuthor($slug: String!, $perPage: Int! = 10, $after: String = \"\") {\n  authors: coAuthors(where: {name: [$slug]}) {\n    nodes {\n      ...AuthorParts\n    }\n  }\n  authorContent(after: $after, first: $perPage, where: {slug: $slug}) {\n    nodes {\n      ... on Email {\n        ...EmailTeaserParts\n        emailLists {\n          nodes {\n            slug\n          }\n        }\n      }\n      ... on Post {\n        ...ArticleTeaserParts\n      }\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n}\n    \n    fragment AuthorParts on CoAuthor {\n  avatar\n  bio\n  emeritus\n  email\n  facebook\n  firstName\n  id\n  instagram\n  lastName\n  linkedin\n  name\n  organization\n  pgp\n  shortBio\n  title\n  twitter\n  type\n  url\n  username\n  website\n}\n    \n\n    fragment EmailTeaserParts on Email {\n  id\n  dateGmt\n  emailId\n  featuredImage {\n    ...MediaParts\n  }\n  link\n  slug\n  segment\n  socialImage {\n    ...MediaParts\n  }\n  seoTitle\n  socialDescription\n  socialTitle\n  subject\n  title\n  authors: coAuthors {\n    nodes {\n      ...AuthorParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "
    }
    return get_graphql_query(gql_query)


def get_guides():
    # Returns an error unless per perPage=12 and postsPerGuide=1
    gql_query = {
        "operationName": "Guides",
        "variables": {"before": "", "perPage": 12, "postsPerGuide": 1, "search": "NULL"},
        "query":"\n    query Guides($before: String = \"\", $perPage: Int = 10, $postsPerGuide: Int = 1, $search: String) {\n  guides(\n    before: $before\n    last: $perPage\n    where: {search: $search, orderby: TERM_ID}\n  ) {\n    nodes {\n      ...GuideParts\n      posts(last: $postsPerGuide) {\n        nodes {\n          ...ArticleTeaserParts\n        }\n      }\n    }\n    pageInfo {\n      hasPreviousPage\n      startCursor\n    }\n  }\n}\n    \n    fragment GuideParts on Guide {\n  id\n  guideId\n  hasEssentials\n  link\n  count\n  description\n  shortDescription\n  name\n  slug\n  featuredImage {\n    ...MediaParts\n  }\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n  colors\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    \n\n    fragment ArticleTeaserParts on Post {\n  __typename\n  bulletin {\n    campaign {\n      id\n      logo\n      name\n      slug\n    }\n    sponsor {\n      name\n    }\n    clientTracking {\n      article\n      elsewhere\n      logo\n    }\n  }\n  contentType {\n    node {\n      name\n    }\n  }\n  dateGmt\n  editions {\n    nodes {\n      name\n      slug\n    }\n  }\n  featuredImage {\n    ...MediaParts\n  }\n  guides {\n    nodes {\n      name\n    }\n  }\n  id\n  kicker\n  link\n  postId\n  serieses {\n    nodes {\n      name\n    }\n  }\n  title\n  trailerVideo {\n    ...VideoParts\n  }\n  video {\n    ...VideoParts\n  }\n}\n    \n\n    fragment VideoParts on VideoData {\n  id\n  duration\n  episode\n  playlistId\n  season\n  type\n}\n    "}
    return get_graphql_query(gql_query)


def get_guides_by_topic(slug_list):
    gql_query = {
        "operationName": "GuidesByTopic",
        "variables": {"perPage": 50, "slug": slug_list},
        "query": "\n    query GuidesByTopic($perPage: Int! = 50, $slug: [String]!) {\n  topics(where: {slug: $slug}) {\n    nodes {\n      id\n      name\n      slug\n      guides(last: $perPage) {\n        nodes {\n          ...GuideParts\n        }\n      }\n    }\n  }\n}\n    \n    fragment GuideParts on Guide {\n  id\n  guideId\n  hasEssentials\n  link\n  count\n  description\n  shortDescription\n  name\n  slug\n  featuredImage {\n    ...MediaParts\n  }\n  socialImage {\n    ...MediaParts\n  }\n  socialTitle\n  colors\n  headerImages {\n    layer\n    size\n    image {\n      ...MediaParts\n    }\n  }\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    "}
    return get_graphql_query(gql_query)


def get_topics():
    gql_query = {
        "operationName": "Topics",
        "variables": {},
        "query": "\n    query Topics {\n  topics {\n    nodes {\n      ...TopicParts\n    }\n  }\n}\n    \n    fragment TopicParts on Topic {\n  description\n  featuredImage {\n    ...MediaParts\n  }\n  id\n  link\n  name\n  shortDescription\n  slug\n  topicId\n}\n    \n\n    fragment MediaParts on MediaItem {\n  altText\n  caption\n  credit\n  id\n  mediaDetails {\n    height\n    width\n  }\n  mediaItemUrl\n  sourceUrl\n  title\n}\n    "}
    gql_json = get_graphql_query(gql_query)
    topics = []
    if gql_json:
        for it in gql_json['data']['topics']['nodes']:
            topics.append(it['slug'])
    return topics


def get_feed(args, save_debug=False):
    posts = []
    feed_title = ''
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 0:
        if paths[-1] == 'feed':
            return rss.get_feed(args, save_debug, get_content)
        if paths[0] == 'discover':
            del paths[0]
        if paths[0] == 'latest':
            del paths[0]

    if len(paths) == 0:
        gql_json = get_latest_articles('QUARTZ')
        if gql_json:
            feed_title = 'QZ.com'
            posts = gql_json['data']['posts']['nodes']
    elif paths[0] == 'obsessions':
        gql_json = get_obsessions()
        if gql_json:
            feed_title = 'QZ.com | Obsessions'
            for it in gql_json['data']['menuItems']['nodes']:
                posts += it['connectedObject']['posts']['nodes']
    elif paths[0] == 'topic':
        gql_json = get_articles_by_topic([paths[1]])
        if gql_json:
            posts = gql_json['data']['topics']['nodes'][0]['posts']['nodes']
    elif paths[0] == 'se':
        gql_json = get_articles_by_series([paths[1]])
        if gql_json:
            posts = gql_json['data']['serieses']['nodes'][0]['posts']['nodes']
    elif paths[0] == 'author':
        gql_json = get_content_by_author(paths[1])
        if gql_json:
            feed_title = 'QZ.com | ' + gql_json['data']['authors']['nodes'][0]['name']
            posts = gql_json['data']['authorContent']['nodes']
    elif paths[0] == 'emails':
        if len(paths) == 1:
            gql_json = get_emails_by_tag(["show-email-in-feeds"])
            if gql_json:
                posts = gql_json['data']['emails']['nodes']
        else:
            gql_json = get_emails_by_list(paths[1])
            if gql_json:
                posts = gql_json['data']['emailLists']['nodes'][0]['emails']['nodes']
    elif paths[0] == 'guides':
        if len(paths) == 1:
            gql_json = get_guides()
            if gql_json:
                for it in gql_json['data']['guides']['nodes']:
                    posts += it['posts']['nodes']
        else:
            topics = get_topics()
            if paths[1] in topics:
                gql_json = get_articles_by_topic([paths[1]])
    elif paths[0] == 'guide':
        gql_json = get_articles_by_guide([paths[1]])
        if gql_json:
            posts = gql_json['data']['guides']['nodes'][0]['posts']['nodes']
            feed_title = 'QZ.com | ' + gql_json['data']['guides']['nodes'][0]['name']
    elif paths[0] == 'trending':
        trending_json = utils.get_url_json('https://sitemap-data.qz.com/popular-articles-quartz.json')
        article_ids = []
        if trending_json:
            for it in trending_json:
                article_ids.append(it['ArticleID'])
        gql_json = get_articles_by_id(article_ids)
    elif paths[-1] == 'latest':
        gql_json = get_latest_articles(paths[0])
    elif paths[0] == 'work' or paths[0] == 'africa' or paths[0] == 'india' or paths[0] == 'japan':
        gql_json = get_latest_articles(paths[0])
        if gql_json:
            feed_title = 'QZ.com | {}'.format(paths[0].title())
            posts = gql_json['data']['posts']['nodes']
    else:
        gql_json = None

    # TODO: featured

    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed_items = []
    for post in posts:
        if save_debug:
            logger.debug('getting content for ' + post['link'])
        if post.get('blocks'):
            item = get_item(post, args, save_debug)
        else:
            item = get_content(post['link'], args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True).copy()
    return feed