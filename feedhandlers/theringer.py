import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import spotify

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, site_json, width=1080):
    return 'https://www.theringer.com/_next/image?url={}&w={}&q=75&dpl={}'.format(quote_plus(img_src), width, site_json['buildId'])


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
        query = '?wordpressNode=' + '&wordpressNode='.join(paths)
    next_url = '{}://{}/_next/data/{}{}.json{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
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


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if '/podcasts/' in url and next_data['pageProps']['__TEMPLATE_QUERY_DATA__'].get('episode'):
        return get_episode_content(next_data['pageProps']['__TEMPLATE_QUERY_DATA__']['episode'], args, site_json, save_debug)
    elif next_data['pageProps']['__TEMPLATE_QUERY_DATA__'].get('post'):
        return get_post_content(next_data['pageProps']['__TEMPLATE_QUERY_DATA__']['post'], 'https://www.theringer.com' + next_data['pageProps']['__SEED_NODE__']['uri'], args, site_json, save_debug)

    logger.warning('unknown content in ' + url)
    return None


def get_episode_content(episode_json, args, site_json, save_debug):
    item = {}
    item['id'] = episode_json['databaseId']
    item['url'] = 'https://www.theringer.com' + episode_json['uri']
    item['title'] = episode_json['title']

    if episode_json.get('date'):
        dt_loc = datetime.fromisoformat(episode_json['date'])
    else:
        dt_loc = datetime.fromisoformat(episode_json['episodeSettings']['releaseDate'].replace('+00:00', ''))
    tz_loc = pytz.timezone(config.local_tz)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['authors'] = [{"name": episode_json['episodeSettings']['show']['node']['title']}]
    item['author'] = {
        "name": episode_json['episodeSettings']['show']['node']['title'],
        "url": "https://www.theringer.com" + episode_json['episodeSettings']['show']['node']['uri']
    }
    if episode_json['episodeSettings'].get('creators') and episode_json['episodeSettings']['creators'].get('nodes'):
        item['authors'] += [{"name": x['name']} for x in episode_json['episodeSettings']['creators']['nodes']]
        if len(item['authors']) > 1:
            item['author']['name'] += ' with ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors'][1:]]))

    item['tags'] = [x['name'] for x in episode_json['categories']['nodes']]

    if episode_json.get('excerpt'):
        item['summary'] = episode_json['excerpt']

    item['content_html'] = ''
    if episode_json['episodeSettings'].get('youtubeId'):
        item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + episode_json['episodeSettings']['youtubeId'])
    elif episode_json.get('featuredImage') and episode_json['featuredImage'].get('node'):
        item['image'] = resize_image(episode_json['featuredImage']['node']['sourceUrl'], site_json)
        if 'embed' not in args:
            captions = []
            if episode_json['featuredImage']['node'].get('caption'):
                captions.append(episode_json['featuredImage']['node']['caption'])
            if episode_json['featuredImage']['node'].get('credits'):
                captions.append(episode_json['featuredImage']['node']['credits'])
            item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))

    if episode_json['episodeSettings'].get('spotifyId'):
        # TODO: use embed link since the Spotify episodes are DRM protected
        # audio_src = 'https://open.spotify.com/episode/' + episode_json['episodeSettings']['spotifyId']
        audio_src = 'https://embed-standalone.spotify.com/embed/episode/' + episode_json['episodeSettings']['spotifyId']
        poster = resize_image(episode_json['episodeSettings']['show']['node']['featuredImage']['node']['sourceUrl'], site_json, 640)
        if 'image' not in item:
            item['image'] = poster
        duration = 60 * episode_json['episodeSettings']['watchTime']
        if episode_json['episodeSettings'].get('youtubeId'):
            desc = '<a href="{}">Watch on Youtube</a>'.format('https://www.youtube.com/watch?v=' + episode_json['episodeSettings']['youtubeId'])
        else:
            desc = ''
        item['content_html'] = utils.add_audio(audio_src, poster, item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], duration, audio_type='audio_link', desc=desc)
    else:
        logger.warning('unknown podcast episode source in ' + item['url'])

    if 'embed' not in args and episode_json.get('content'):
        item['content_html'] += episode_json['content']
    return item


def get_post_content(post_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = post_json['databaseId']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['authors'] = [{"name": x['name']} for x in post_json['articleSettings']['creators']['nodes']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = [x['name'] for x in post_json['articleSettings']['primaryTopic']['nodes']]

    item['content_html'] = ''
    if post_json.get('alternativeTitleDesc') and post_json['alternativeTitleDesc'].get('description'):
        item['summary'] = post_json['alternativeTitleDesc']['description']
    elif post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        item['image'] = resize_image(post_json['featuredImage']['node']['sourceUrl'], site_json)
        captions = []
        if post_json['featuredImage']['node'].get('caption'):
            captions.append(post_json['featuredImage']['node']['caption'])
        if post_json['featuredImage']['node'].get('credits'):
            captions.append(post_json['featuredImage']['node']['credits'])
        item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    for block in post_json['editorBlocks']:
        if block['__typename'] == 'RingerBlocksHero':
            if block['attributes'].get('content'):
                item['content_html'] = '<p><em>' + block['attributes']['content'] + '</em></p>' + item['content_html']
        else:
            item['content_html'] += format_block(block, post_json['articleContent'].get('footnotes'), site_json)

    if post_json['articleContent'].get('footnotes'):
        def add_footnote(matchobj):
            return matchobj.group(2) + '<sup><a href="#footnote-{0}">{0}</a></sup>'.format(matchobj.group(1))
        item['content_html'] = re.sub(r'<span[^>]*?data-footnote="([\d+])"[^>]*?>([^>]+?)</span>', add_footnote, item['content_html'])
        item['content_html'] += '<h2>Footnotes:</h2>'
        for it in post_json['articleContent']['footnotes']:
            item['content_html'] += '<div id="footnote-{0}"><div style="float:left;">{0}.&nbsp;</div>'.format(it['title']) + it['text'] + '</div><div style="clear:left;"></div>'

    return item

def sub_footnote(matchobj):
    return matchobj.group(2) + '<sup><a href="#footnote-{0}">{0}</a></sup>'.format(matchobj.group(1))

def format_block(block, footnotes, site_json):
    block_html = ''
    if block['__typename'] == 'CoreParagraph':
        if block['attributes'].get('content'):
            if block['attributes']['dropCap']:
                m = re.search(r'^(\W*\w)', block['attributes']['content'])
                block_html += '<p><span style="float:left; font-size:4em; line-height:0.8em;">' + m.group(1) + '</span>'
                block_html += re.sub(r'^(\W*\w)', '', block['attributes']['content']) + '</p><span style="clear:left;"></span>'
            else:
                block_html += '<p>' + block['attributes']['content'] + '</p>'
            if 'ringer-blocks-format-footnote' in block['attributes']['content']:
                block_html = re.sub(r'<span[^>]*?data-footnote="([\d+])"[^>]*?>([^>]+?)</span>', sub_footnote, block_html)
                for m in re.findall(r'data-footnote="([\d+])"', block['attributes']['content']):
                    footnote = next((it for it in footnotes if it['title'] == m), None)
                    block_html += '<details id="footnote-{0}" style="font-size:0.8em; margin-left:2em;"><summary>{0}</summary>{1}</details>'.format(footnote['title'], footnote['text'])
    elif block['__typename'] == 'RingerBlocksHeading':
        if block['attributes']['level'] > 3:
            tag = 'h3'
        else:
            tag = 'h' + str(block['attributes']['level'])
        block_html += '<{0}>{1}</{0}>'.format(tag, block['attributes']['content'])
    elif block['__typename'] == 'CoreImage':
        img_src = resize_image(block['image']['sourceUrl'], site_json)
        captions = []
        if block['image'].get('caption'):
            captions.append(re.sub(r'^(<br>|<p>)|(<br>|</p>$)', '', block['image']['caption'].strip()))
        elif block['attributes'].get('caption'):
            captions.append(re.sub(r'^(<br>|<p>)|(<br>|</p>$)', '', block['attributes']['caption'].strip()))
        if block['image'].get('credits'):
            captions.append(block['image']['credits'])
        block_html += utils.add_image(img_src, ' | '.join(captions))
    elif block['__typename'] == 'CoreList':
        if block['attributes']['ordered'] == True:
            tag = 'ol'
        else:
            tag = 'ul'
        if block['attributes'].get('values'):
            block_html += '<{0}>{1}</{0}>'.format(tag, block['attributes']['values'])
        else:
            logger.warning('unhandled CoreList values')
    elif block['__typename'] == 'CoreListItem':
        if block.get('attributes'):
            logger.warning('unhandled CoreListItem')
    elif block['__typename'] == 'CoreTable':
        if block['attributes'].get('title'):
            block_html += '<div style="text-align:center; padding:8px; font-size:1.1em; font-weight:bold; background-color:rgb(0 177 18); color:black;">' + block['attributes']['title'] + '</div>'
        soup = BeautifulSoup(block['renderedHtml'], 'html.parser')
        soup.table['style'] = 'width:100%; border-collapse:collapse;'
        for i, it in enumerate(soup.find_all('tr')):
            if i == 0:
                it['style'] = 'background-color:black; color:white;'
            elif i % 2 == 0:
                it['style'] = 'background-color:light-dark(#ccc, #333);'
            else:
                it['style'] = ''
        for it in soup.find_all(['td', 'th']):
            it['style'] = 'padding:12px 8px; border:1px solid black;'
        it = soup.table.find_parent('figure')
        if it:
            it.unwrap()
        block_html += str(soup)
    elif block['__typename'] == 'CoreEmbed':
        if block['attributes'].get('url'):
            block_html += utils.add_embed(block['attributes']['url'])
        else:
            logger.warning('unhandled CoreEmbed provider ' + block['attributes']['providerNameSlug'])
    elif block['__typename'] == 'RingerBlocksYoutubeEmbed':
        block_html += utils.add_embed(block['attributes']['link'])
    elif block['__typename'] == 'RingerBlocksMediaCard':
        if block['attributes']['subtype'] == 'episode' and block['post']['episodeSettings'].get('spotifyId'):
            block_html += utils.add_embed(block['post']['episodeSettings']['url'])
        elif block['attributes']['subtype'] == 'article':
            card = get_post_content(block['post'], 'https://www.theringer.com' + block['post']['uri'], {"embed": True}, site_json, False)
            block_html += card['content_html']
        else:
            logger.warning('unhandled RingerBlocksMediaCard')
    # elif block['__typename'] == 'RingerBlocksEndingParagraph':
        # This content is repeated?
    #     for blk in block['innerBlocks']:
    #         block_html += format_block(blk, site_json)
    elif block['__typename'] == 'RingerBlocksAdvertisement' or block['__typename'] == 'RingerBlocksRelatedContent' or block['__typename'] == 'RingerBlocksRelatedContentTab' or block['__typename'] == 'RingerBlocksRelatedContentCard':
        pass
    else:
        logger.warning('unhandled block type ' + block['__typename'])
    return block_html


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'topic' in paths:
        variables = {
            "limit": 10,
            "medium": None,
            "categories": [
                paths[-1]
            ],
            "creators": [],
            "afterDate":"",
            "beforeDate":""
        }
        # query = "query: query LATEST_POSTS($limit: Int! $after: String $medium: String $categories: [String] $creators: [String] $beforeDate: String $afterDate: String) { contentNodes( where: {type: [\"episode\" \"post\"] beforeReleaseDate: $beforeDate afterReleaseDate: $afterDate topics: $categories creators: $creators medium: $medium orderby: {field: RELEASE_DATE order: DESC}} after: $after first: $limit ) { pageInfo { hasNextPage hasPreviousPage startCursor endCursor } nodes { ... on Post { ...PostFragment } ... on Episode { ...EpisodeFragment } } } } fragment EpisodeFragment on Episode { __typename id title uri status databaseId alternativeTitleDesc { titleSmall titleMedium } episodeSettings { releaseDate watchTime spotifyId youtubeId url primaryPlayAction medium { nodes { __typename name slug } } primaryTopic { __typename nodes { ...CategoryFragment } } show { node { ... on Show { __typename title alternativeTitleDesc { titleSmall titleMedium } uri id featuredImage { node { ...ImageFragment } } } } } } episodeContent { teaser { node { altText mediaItemUrl mimeType mediaDetails { height width } } } showLogoOverride { node { ...ImageFragment } } } featuredImage { node { ...ImageFragment } } categories { nodes { ...CategoryFragment } } } fragment ImageFragment on MediaItem { id altText caption credits mediaType sourceUrl srcSet focalpointX focalpointY mediaDetails { height width } } fragment CategoryFragment on Category { __typename id parentId slug name uri description topic { colorPicker image { node { ...ImageFragment } } } } fragment PostFragment on Post { __typename id title excerpt uri databaseId dateGmt articleSettings { creators { nodes { ... on Creator { id name uri creatorSettings { image { node { ...ImageFragment } } } } } } releaseDate readTime primaryTopic { nodes { ...CategoryFragment } } } alternativeTitleDesc { titleSmall titleMedium } featuredImage { node { ...ImageFragment } } }"
        query = 'query%20LATEST_POSTS(%24limit%3A%20Int!%20%24after%3A%20String%20%24medium%3A%20String%20%24categories%3A%20%5BString%5D%20%24creators%3A%20%5BString%5D%20%24beforeDate%3A%20String%20%24afterDate%3A%20String)%20%7B%20contentNodes(%20where%3A%20%7Btype%3A%20%5B%22episode%22%20%22post%22%5D%20beforeReleaseDate%3A%20%24beforeDate%20afterReleaseDate%3A%20%24afterDate%20topics%3A%20%24categories%20creators%3A%20%24creators%20medium%3A%20%24medium%20orderby%3A%20%7Bfield%3A%20RELEASE_DATE%20order%3A%20DESC%7D%7D%20after%3A%20%24after%20first%3A%20%24limit%20)%20%7B%20pageInfo%20%7B%20hasNextPage%20hasPreviousPage%20startCursor%20endCursor%20%7D%20nodes%20%7B%20...%20on%20Post%20%7B%20...PostFragment%20%7D%20...%20on%20Episode%20%7B%20...EpisodeFragment%20%7D%20%7D%20%7D%20%7D%20fragment%20EpisodeFragment%20on%20Episode%20%7B%20__typename%20id%20title%20uri%20status%20databaseId%20alternativeTitleDesc%20%7B%20titleSmall%20titleMedium%20%7D%20episodeSettings%20%7B%20releaseDate%20watchTime%20spotifyId%20youtubeId%20url%20primaryPlayAction%20medium%20%7B%20nodes%20%7B%20__typename%20name%20slug%20%7D%20%7D%20primaryTopic%20%7B%20__typename%20nodes%20%7B%20...CategoryFragment%20%7D%20%7D%20show%20%7B%20node%20%7B%20...%20on%20Show%20%7B%20__typename%20title%20alternativeTitleDesc%20%7B%20titleSmall%20titleMedium%20%7D%20uri%20id%20featuredImage%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20%7D%20%7D%20%7D%20%7D%20episodeContent%20%7B%20teaser%20%7B%20node%20%7B%20altText%20mediaItemUrl%20mimeType%20mediaDetails%20%7B%20height%20width%20%7D%20%7D%20%7D%20showLogoOverride%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20%7D%20featuredImage%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20categories%20%7B%20nodes%20%7B%20...CategoryFragment%20%7D%20%7D%20%7D%20fragment%20ImageFragment%20on%20MediaItem%20%7B%20id%20altText%20caption%20credits%20mediaType%20sourceUrl%20srcSet%20focalpointX%20focalpointY%20mediaDetails%20%7B%20height%20width%20%7D%20%7D%20fragment%20CategoryFragment%20on%20Category%20%7B%20__typename%20id%20parentId%20slug%20name%20uri%20description%20topic%20%7B%20colorPicker%20image%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20%7D%20%7D%20fragment%20PostFragment%20on%20Post%20%7B%20__typename%20id%20title%20excerpt%20uri%20databaseId%20dateGmt%20articleSettings%20%7B%20creators%20%7B%20nodes%20%7B%20...%20on%20Creator%20%7B%20id%20name%20uri%20creatorSettings%20%7B%20image%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20%7D%20%7D%20%7D%20%7D%20releaseDate%20readTime%20primaryTopic%20%7B%20nodes%20%7B%20...CategoryFragment%20%7D%20%7D%20%7D%20alternativeTitleDesc%20%7B%20titleSmall%20titleMedium%20%7D%20featuredImage%20%7B%20node%20%7B%20...ImageFragment%20%7D%20%7D%20%7D'
        gql_url = 'https://wp.theringer.com/graphql?operationName=LATEST_POSTS&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&query=' + query
        gql_json = utils.get_url_json(gql_url)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        content_nodes = gql_json['data']['contentNodes']['nodes']
    elif 'creator' in paths:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        content_nodes = next_data['pageProps']['__TEMPLATE_QUERY_DATA__']['nodeByUri']['contentNodes']['nodes']
    else:
        return None

    n = 0
    feed_items = []
    for node in content_nodes:
        node_url = 'https://www.theringer.com' + node['uri']
        if save_debug:
            logger.debug('getting content from ' + node_url)
        if node['__typename'] == 'Episode':
            item = get_episode_content(node, args, site_json, save_debug)
        else:
            item = get_content(node_url, args, site_json, save_debug)
        item = get_content(node_url, args, site_json, save_debug)
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
