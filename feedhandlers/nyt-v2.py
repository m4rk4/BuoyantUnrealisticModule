import base64, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss, wirecutter

import logging

logger = logging.getLogger(__name__)


def format_text(block):
    start_tags = []
    end_tags = []
    if 'formats' in block:
        for fmt in block['formats']:
            if fmt['__typename'] == 'LinkFormat':
                start_tags.append('<a href="{}">'.format(fmt['url']))
                end_tags.insert(0, '</a>')
            elif fmt['__typename'] == 'BoldFormat':
                start_tags.append('<b>')
                end_tags.insert(0, '</b>')
            elif fmt['__typename'] == 'ItalicFormat':
                start_tags.append('<i>')
                end_tags.insert(0, '</i>')
            else:
                logger.warning('Unhandled format type ' + fmt['__typename'])

    text_html = ''.join(start_tags)
    if 'text' in block:
        text_html += block['text']
    elif 'text@stripHtml' in block:
        text_html += block['text@stripHtml']
    else:
        logger.warning('no text in ' + block['__typename'])
    text_html += ''.join(end_tags)
    return text_html


def render_block(block, full_header=False, headline_url=''):
    block_html = ''
    if block['__typename'] == 'Dropzone' or block['__typename'] == 'EmailSignupBlock':
        pass

    elif block['__typename'] == 'TextInline':
        block_html += format_text(block)

    elif block['__typename'] == 'TextOnlyDocumentBlock':
        block_html += block['text']

    elif block['__typename'] == 'ParagraphBlock':
        block_html += '<p>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</p>'

    elif block['__typename'] == 'CapsuleBlock':
        block_html += render_block(block['capsuleContent'])

    elif block['__typename'] == 'Capsule':
        block_html += render_block(block['body'])

    elif block['__typename'] == 'DocumentBlock':
        for blk in block['content']:
            block_html += render_block(blk, full_header, headline_url)

    elif block['__typename'] == 'ListBlock':
        if block['style'] == 'UNORDERED':
            block_tag = 'ul'
        else:
            block_tag = 'ol'
        block_html += '<{}>'.format(block_tag)
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</{}>'.format(block_tag)

    elif block['__typename'] == 'ListItemBlock':
        block_html += '<li>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</li>'

    elif block['__typename'] == 'HeaderBasicBlock' or block['__typename'] == 'HeaderFullBleedHorizontalBlock'  or block['__typename'] == 'HeaderFullBleedVerticalBlock' or block['__typename'] == 'HeaderMultimediaBlock':
        if full_header:
            if block.get('headline'):
                if headline_url:
                    block_html += '<a href="{}">{}</a>'.format(headline_url, render_block(block['headline']))
                else:
                    block_html += render_block(block['headline'])
            if block.get('timestampBlock'):
                block_html += render_block(block['timestampBlock'])
        if block.get('byline'):
            block_html += render_block(block['byline'], full_header)
        if block.get('summary'):
            block_html += render_block(block['summary'])
        if block.get('ledeMedia'):
            block_html += render_block(block['ledeMedia'])
        if block.get('media'):
            block_html += render_block(block['media'])

    elif re.search(r'Heading\dBlock', block['__typename']):
        m = re.search(r'Heading(\d)Block', block['__typename'])
        block_html += '<h{}>'.format(m.group(1))
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</h{}>'.format(m.group(1))

    elif block['__typename'] == 'DetailBlock' or block['__typename'] == 'SummaryBlock':
        block_html += '<p><em>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</em></p>'

    elif block['__typename'] == 'BylineBlock':
        if full_header:
            block_html += '<p><strong>'
            for blk in block['bylines']:
                block_html += render_block(blk)
            block_html += '</strong>'
            if block.get('role'):
                block_html += '<br/><em><small>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
            block_html += '</small></em></p>'
        else:
            if block.get('role'):
                block_html += '<p><em><small>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
                block_html += '</small></em></p>'

    elif block['__typename'] == 'Byline':
        block_html += block['prefix'] + ' '
        creators = []
        for it in block['creators']:
            creators.append(it['displayName'])
        block_html += re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(creators))

    elif block['__typename'] == 'TimestampBlock':
        dt = datetime.fromisoformat(block['timestamp'].replace('Z', '+00:00'))
        block_html += '<p>' + utils.format_display_date(dt) + '</p>'

    elif block['__typename'] == 'BlockquoteBlock':
        quote = ''
        for blk in block['content']:
            quote += render_block(blk)
        block_html += utils.add_blockquote(quote)

    elif block['__typename'] == 'ImageBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'DiptychBlock':
        for key, blk in block.items():
            if key.startswith('image'):
                block_html += render_block(blk)
            elif key not in ['__typename', 'size']:
                logger.warning('unhandled DiptychBlock key ' + key)

    elif block['__typename'] == 'UnstructuredBlock':
        if block.get('mediaRefs'):
            for blk in block['mediaRefs']:
                block_html += render_block(blk)
        elif block['dataType'] == 'ExperimentalBlock_DocPromo':
            data_json = json.loads(block['data'])
            block_html += utils.add_blockquote('<a href="https://www.nytimes.com/{}"><b>{}</b></a><br/>{}'.format(data_json['documentData']['publishPath'], data_json['documentData']['name'], data_json['documentData']['description']))
        else:
            logger.warning('unhandled UnstructuredBlock')

    elif block['__typename'] == 'Image':
        images = []
        for it in block['crops']:
            images += it['renditions']
        image = utils.closest_dict(images, 'width', 1000)
        captions = []
        if block.get('caption'):
            it = render_block(block['caption']).strip()
            if it:
                captions.append(it)
        if block.get('credit'):
            captions.append(block['credit'])
        block_html += utils.add_image(image['url'], ' | '.join(captions))

    elif block['__typename'] == 'VideoBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Video':
        for it in block['renditions']:
            if re.search(r'video_480p_mp4', it['type']):
                video = it
                break
        for it in block['promotionalMedia']['crops']:
            if it['name'] == 'MASTER':
                image = utils.closest_dict(it['renditions'], 'width', 1000)
        caption = block['summary'] + ' | ' + block['promotionalMedia']['credit']
        block_html += utils.add_video(video['url'], 'video/mp4', image['url'], caption)

    elif block['__typename'] == 'AudioBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Audio':
        if block.get('promotionalMedia'):
            image = block['promotionalMedia']['crops'][0]['renditions'][0]
            poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(image['url']))
        else:
            poster = '{}/image?width=64&height=64&overlay=audio'.format(config.server)
        block_html += '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}'.format(block['fileUrl'], poster, block['fileUrl'], block['headline']['default'], block['summary'])
        if block.get('podcastSeries'):
            block_html += '<br/><a href="https://www.nytimes.com/column/{}"><small>{}</small></a>'.format(block['podcastSeries']['name'], block['podcastSeries']['title'])
        block_html += '</td></tr></table>'

    elif block['__typename'] == 'GridBlock':
        block_html += '<div><strong>{}</strong><br/>'.format(block['caption'])
        for blk in block['gridMedia']:
            block_html += render_block(blk)
        block_html += '</div>'

    elif block['__typename'] == 'InteractiveBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Interactive':
        for it in block['promotionalMedia']['spanImageCrops']:
            if it['name'] == 'MASTER':
                image = utils.closest_dict(it['renditions'], 'width', 400)
        block_html += '<table><tr><td><a href="{}"><img src="{}" width="160px"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}</td></tr></table>'.format(block['url'], image['url'], block['url'], block['headline']['default'], block['summary'])

    elif block['__typename'] == 'EmbeddedInteractive':
        soup = BeautifulSoup(block['html'], 'html.parser')
        if block['appName'] == 'Datawrapper':
            it = soup.find('iframe')
            if it:
                block_html += utils.add_embed(it['src'])
            else:
                logger.warning('unhandled Datawrapper embed')
        elif block['appName'] == 'Pilot':
            m = re.search(r'window\.bursts\.state\[\'[^\']+\'\] = "([^"]+)"', block['html'])
            if m:
                burst_json = json.loads(unquote_plus(m.group(1)))
                block_html += '<hr/>'
                for blk in burst_json['title']['content']:
                    block_html += render_block(blk)
                for it in burst_json['items']:
                    for blk in it['body']['content']:
                        block_html += render_block(blk)
                block_html += '<hr/>'
            else:
                logger.warning('unhandled card in Pilot EmbeddedInteractive')
        elif soup.find('blockquote', class_='tiktok-embed'):
            block_html += utils.add_embed(soup.blockquote['cite'])
        elif block.get('slug') and 'burst-video' in block['slug']:
            #video_json = get_video_json(block['uri'], True)
            logger.warning('unhandled burst-video')
        elif block['appName']:
            logger.warning('unhandled EmbeddedInteractive ' + block['appName'])
        else:
            embed_html = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{}</body></html>'.format(block['html'])
            embed_b64 = base64.b64encode(embed_html.encode('utf-8'))
            block_html += '<h4><a href="data:text/html;base64,{}">View embedded content</a></h4>'.format(embed_b64.decode('utf-8'))

    elif block['__typename'] == 'YouTubeEmbedBlock':
        block_html += utils.add_embed('https://www.youtube.com/embed/' + block['youTubeId'])

    elif block['__typename'] == 'TwitterEmbedBlock':
        block_html += utils.add_embed(block['twitterUrl'])

    elif block['__typename'] == 'InstagramEmbedBlock':
        block_html += utils.add_embed(block['instagramUrl'])

    elif block['__typename'] == 'LabelBlock':
        block_html += '<h4>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</h4>'

    elif block['__typename'] == 'RuleBlock':
        block_html += '<hr/>'

    elif block['__typename'] == 'LineBreakInline':
        block_html += '<br/>'

    elif block['__typename'] == 'RelatedLinksBlock':
        if block.get('title'):
            block_html += '<h3 style="margin-bottom:0;">'
            for blk in block['title']:
                block_html += render_block(blk)
            block_html += '</h3>'
        if block.get('description'):
            block_html += '<p style="font-style:italic; margin-top:0;">'
            for blk in block['description']:
                block_html += render_block(blk)
            block_html += '</p>'

        if block.get('related'):
            block_html += '<ul style="margin-top:0;">'
            for it in block['related']:
                block_html += '<li><a href="{}">{}</a></li>'.format(it['url'], it['headline']['default'])
            block_html += '</ul>'

    else:
        logger.warning('unhandled content block ' + block['__typename'])

    return block_html


def get_video_json(video_id, save_debug):
    # From: https://static01.nyt.com/video-static/vhs3/vhs.min.js
    data = {
        "query": "\nquery VideoQuery($id: String!) {\n  video(id: $id) {\n    ...on Video {\n      __typename\n      id\n      bylines {\n        renderedRepresentation\n      }\n      contentSeries\n      cues {\n        name\n        type\n        timeIn\n        timeOut\n      }\n      duration\n      embedded\n      headline {\n        default\n      }\n      firstPublished\n      lastModified\n      is360\n      isLive\n      liveUrls\n      playlist {\n        headline {\n          default\n        }\n        promotionalHeadline\n        url\n        sourceId\n        section {\n          displayName\n        }\n        videos(first: 10) {\n          edges @filterEmpty {\n            node {\n              id\n              sourceId\n              duration\n              section {\n                id\n                name\n              }\n              headline {\n                default\n              }\n              renditions {\n                url\n                type\n              }\n              url\n              promotionalMedia {\n                ... on Image {\n                  crops(cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE]) {\n                    renditions {\n                      name\n                      width\n                      height\n                      url\n                    }\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n      promotionalHeadline\n      promotionalMedia {\n        ... on Image {\n          crops (cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE, THREE_BY_TWO, TWO_BY_THREE, FLEXIBLE]) {\n            name\n            renditions {\n              name\n              width\n              height\n              url\n            }\n          }\n        }\n      }\n      promotionalSummary\n      renditions {\n        type\n        width\n        height\n        url\n        bitrate\n      }\n      section {\n        name\n      }\n      shortUrl\n      sourceId\n      subsection {\n        name\n      }\n      summary\n      timesTags {\n        __typename\n        displayName\n        isAdvertisingBrandSensitive\n        vernacular\n      }\n      uri\n      url\n    }\n  }\n}",
        "variables": {"id": video_id}
    }
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "nyt-app-type": "vhs",
        "nyt-app-version": "v3.52.2",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuNIzKBOFB77aT/jN/FQ+/QVKWq5V1ka1AYmCR9hstz1pGNPH5ajOU9gAqta0T89iPnhjwla+3oec/Z3kGjxbpv6miQXufHFq3u2RC6HyU458cLat5kVPSOQCe3VVB5NRpOlRuwKHqn0txfxnwSSj8mqzstR997d3gKB//RO9zE16y3PoWlDQXkASngNJEWvL19iob/xwAkfEWCjyRILWFY0JYX3AvLMSbq7wsqOCE5srJpo7rRU32zsByhsp1D5W9OYqqwDmflsgCEQy2vqTsJjrJohuNg+urMXNNZ7Y3naMoqttsGDrWVxtPBafKMI8pM2ReNZBbGQsQXRzQNo7+QIDAQAB",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', json_data=data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/video.json')
    return gql_json['data']['video']


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if site_json.get('exclude_paths') and list(set(paths) & set(site_json['exclude_paths'])):
        logger.debug('skipping ' + url)
        return None
    elif 'wirecutter' in paths:
        return wirecutter.get_content(url, args, site_json, save_debug)

    article_html = utils.get_url_html(url, user_agent='googlebot')
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    soup = BeautifulSoup(article_html, 'html.parser')

    article_json = None
    if '/video/' in url:
        el = soup.find('meta', attrs={"name": "nyt_uri"})
        if el:
            article_json = get_video_json(el['content'], save_debug)
    else:
        preloaded_data = ''
        el = soup.find('script', string=re.compile(r'window\.__preloadedData'))
        if el:
            preloaded_data = el.string[25:-1]
        else:
            m = re.search(r'<script>window\.__preloadedData = (.+);</script>', article_html)
            if m:
                preloaded_data = m.group(1)
        if not preloaded_data:
            logger.warning('No preloadData found in ' + url)
            return None
        if save_debug:
            utils.write_file(preloaded_data, './debug/debug.txt')

        try:
            preloaded_json = json.loads(preloaded_data.replace(':undefined', ':""'))
        except:
            logger.warning('unable to convert preloadedData to json in ' + url)
            return None
        if save_debug:
            utils.write_file(preloaded_json, './debug/data.json')

        if '/explain/' in url:
            article_json = preloaded_json['initialData']['data']['explainerAsset']
        else:
            article_json = preloaded_json['initialData']['data']['article']

    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']['default']

    dt = datetime.fromisoformat(article_json['firstPublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('bylines'):
        item['author']['name'] = re.sub(r'^By ', '', article_json['bylines'][0]['renderedRepresentation'])
    elif article_json.get('desk'):
        item['author']['name'] = article_json['desk']
    elif '/explain/' in item['url']:
        item['author']['name'] = 'The New York Times Explainer'
    else:
        item['author']['name'] = 'The New York Times'

    if article_json.get('timesTags'):
        item['tags'] = []
        for it in article_json['timesTags']:
            item['tags'].append(it['displayName'])

    item['summary'] = article_json['summary']

    item['content_html'] = ''
    if article_json['__typename'] == 'Video':
        for it in article_json['renditions']:
            if it['type'] == 'video_480p_mp4':
                item['_video'] = it['url']
                break
        for it in article_json['promotionalMedia']['crops']:
            if it['name'] == 'SIXTEEN_BY_NINE':
                item['_image'] = utils.closest_dict(it['renditions'], 'width', 1000)['url']
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
        item['content_html'] += '<p>' + article_json['summary'] + '</p>'

    else:
        if article_json.get('promotionalMedia'):
            if article_json['promotionalMedia']['__typename'] == 'Image':
                crops = article_json['promotionalMedia']['assetCrops']
            else:
                crops = article_json['promotionalMedia']['promotionalMedia']['assetCrops']
            for it in crops:
                if it['name'] == 'MASTER':
                    image = utils.closest_dict(it['renditions'], 'width', 1500)
                    item['_image'] = image['url']
                    break

        if article_json.get('groupings'):
            for group in article_json['groupings']:
                container = next((it for it in group['containers'] if it['name'] == 'feed lede'), None)
            if container:
                for it in container['relations']:
                    item['content_html'] += render_block(it['asset']['body'], True)

        if article_json.get('highlights'):
            item['content_html'] += '<h3>Contents:</h3><ul>'
            for it in article_json['highlights']['edges']:
                item['content_html'] += '<li>{}</li>'.format(it['node']['headline']['default'])
            item['content_html'] += '</ul>'
            for it in article_json['highlights']['edges']:
                item['content_html'] += '<hr/>'
                if it['node']['__typename'] == 'Article':
                    if item['url'] in it['node']['url']:
                        item['content_html'] += render_block(it['node']['body'], True)
                    else:
                        item['content_html'] += render_block(it['node']['body'], True, it['node']['url'])
                else:
                    logger.warning('skipping highlight type {} in {}'.format(it['node']['__typename'], item['url']))

        if article_json.get('sprinkledBody'):
            item['content_html'] += render_block(article_json['sprinkledBody'])

    item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', item['content_html'])
    return item


def get_collection(path):
    data = {
        "operationName": "CollectionsQuery",
        "query": "query CollectionsQuery($id: String!, $first: Int, $cursor: String, $collectionQuery: CollectionStreamQuery, $exclusionMode: StreamExclusionMode, $highlightsListUri: PersonalizedListUri!, $highlightsListFirst: Int, $hasHighlightsList: Boolean!, $isHighEnd: Boolean!) {\n  legacyCollection: workOrLocation(id: $id) {\n    ... on RelocatedWork {\n      targetUrl\n      __typename\n    }\n    ... on LegacyCollection {\n      id\n      ...CollectionsMain_legacyCollection\n      __typename\n    }\n    __typename\n  }\n  lists @include(if: $hasHighlightsList) {\n    personalizedList(\n      listUri: $highlightsListUri\n      first: $highlightsListFirst\n      personalizedListContext: {appType: WEB}\n    ) {\n      ...Rank_lists\n      __typename\n    }\n    __typename\n  }\n  highEndArticles: legacySearch(\n    query: {sort: newest, filterQuery: \"section_name:\\\"real estate\\\" AND data_type:\\\"article\\\"\"}\n  ) @include(if: $isHighEnd) {\n    ...TheHighEnd_legacySearchResult\n    __typename\n  }\n}\n\nfragment Rank_lists on PersonalizedItemsConnection {\n  ...Highlights_lists\n  __typename\n}\n\nfragment Highlights_lists on PersonalizedItemsConnection {\n  ...Connection_pageInfo\n  edges {\n    node {\n      __typename\n      ... on Node {\n        id\n        __typename\n      }\n      ...ShowcaseStory_data\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment ShowcaseStory_data on HasPromotionalProperties {\n  ... on Published {\n    url\n    lastMajorModification\n    __typename\n  }\n  ... on CreativeWork {\n    headline {\n      default\n      __typename\n    }\n    displayProperties {\n      showPublicationDate\n      __typename\n    }\n    summary\n    kicker\n    column {\n      id\n      name\n      __typename\n    }\n    bylines {\n      prefix\n      creators {\n        ... on Person {\n          id\n          displayName\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ... on Article {\n    id\n    printInformation {\n      section\n      page\n      __typename\n    }\n    __typename\n  }\n  ... on Promo {\n    id\n    targetUrl\n    promotionalHeadline\n    promotionalSummary\n    __typename\n  }\n  ...Image_data\n  __typename\n}\n\nfragment Image_data on HasPromotionalProperties {\n  __typename\n  ... on Published {\n    url\n    __typename\n  }\n  promotionalMedia {\n    __typename\n    ... on Video {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...ImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Audio {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...ImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Slideshow {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...ImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Interactive {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...ImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on EmbeddedInteractive {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...ImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Image {\n      id\n      ...ImageFragment_data\n      __typename\n    }\n  }\n}\n\nfragment ImageFragment_data on Image {\n  id\n  caption {\n    text\n    __typename\n  }\n  credit\n  crops(\n    renditionNames: [\"videoLarge\", \"mediumThreeByTwo440\", \"mediumThreeByTwo225\", \"threeByTwoMediumAt2X\", \"hpSmall\", \"thumbLarge\", \"thumbStandard\", \"jumbo\"]\n  ) {\n    renditions {\n      name\n      url\n      width\n      height\n      __typename\n    }\n    __typename\n  }\n  timesTags {\n    vernacular\n    __typename\n  }\n  __typename\n}\n\nfragment Connection_pageInfo on RelayConnection {\n  pageInfo {\n    hasNextPage\n    hasPreviousPage\n    startCursor\n    endCursor\n    __typename\n  }\n  __typename\n}\n\nfragment TheHighEnd_legacySearchResult on LegacySearchResult {\n  hits {\n    ...Connection_pageInfo\n    edges {\n      node {\n        __typename\n        ... on BodegaResult {\n          node {\n            __typename\n            ... on Article {\n              id\n              headline {\n                default\n                __typename\n              }\n              summary\n              kicker\n              lastMajorModification\n              url\n              bylines {\n                prefix\n                creators {\n                  ... on Person {\n                    id\n                    displayName\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              promotionalMedia {\n                __typename\n                ... on Video {\n                  id\n                  promotionalMedia {\n                    ... on Image {\n                      id\n                      ...ImageFragment_data\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                ... on Audio {\n                  id\n                  promotionalMedia {\n                    ... on Image {\n                      id\n                      ...ImageFragment_data\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                ... on Slideshow {\n                  id\n                  promotionalMedia {\n                    ... on Image {\n                      id\n                      ...ImageFragment_data\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                ... on Interactive {\n                  id\n                  promotionalMedia {\n                    ... on Image {\n                      id\n                      ...ImageFragment_data\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                ... on EmbeddedInteractive {\n                  id\n                  promotionalMedia {\n                    ... on Image {\n                      id\n                      ...ImageFragment_data\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                ... on Image {\n                  id\n                  ...ImageFragment_data\n                  __typename\n                }\n              }\n              __typename\n            }\n          }\n          __typename\n        }\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CollectionsMain_legacyCollection on LegacyCollection {\n  id\n  collectionType\n  slug\n  name\n  tone\n  showPicture\n  longDescription\n  bylines {\n    creators {\n      ... on Person {\n        id\n        legacyData {\n          htmlBiography\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  section {\n    id\n    name\n    __typename\n  }\n  subsection {\n    id\n    name\n    __typename\n  }\n  advertisingProperties {\n    sensitivity\n    sponsored\n    __typename\n  }\n  adTargetingParams(clientAdParams: {edn: \"us\", plat: \"web\", prop: \"nyt\"}) {\n    key\n    value\n    __typename\n  }\n  dfpTaxonomyException\n  collectionsPage {\n    ...Rank_page\n    __typename\n  }\n  ...CollectionHelmet_data\n  ...Header_data\n  ...SupplementalHeader_data\n  ...StorylinesHub_data\n  ...Rank_data\n  ...Supplemental_data\n  ...StorylinesMenu_legacyCollection\n  ...Rank_highlights @skip(if: $hasHighlightsList)\n  __typename\n}\n\nfragment CollectionHelmet_data on LegacyCollection {\n  id\n  firstPublished\n  lastModified\n  sourceId\n  url\n  collectionType\n  tagline\n  section {\n    id\n    name\n    displayName\n    url\n    __typename\n  }\n  subsection {\n    id\n    name\n    displayName\n    url\n    __typename\n  }\n  promoMedia: promotionalMedia {\n    __typename\n    ... on Video {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...HelmetImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Slideshow {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...HelmetImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Interactive {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...HelmetImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on EmbeddedInteractive {\n      id\n      promotionalMedia {\n        ... on Image {\n          id\n          ...HelmetImageFragment_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Image {\n      id\n      ...HelmetImageFragment_data\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment HelmetImageFragment_data on Image {\n  id\n  credit\n  crops(\n    cropNames: [SIXTEEN_BY_NINE]\n    renditionNames: [\"videoSixteenByNineJumbo1600\", \"videoSixteenByNine1050\", \"videoSixteenByNine768\"]\n  ) {\n    name\n    renditions {\n      name\n      url\n      width\n      height\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Header_data on LegacyCollection {\n  id\n  name\n  url\n  shortUrl\n  tagline\n  bylines {\n    creators {\n      ... on Person {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            crops(cropNames: SMALL_SQUARE, renditionNames: \"thumbLarge\") {\n              renditions {\n                name\n                url\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  longDescription\n  slug\n  headline {\n    default\n    __typename\n  }\n  language {\n    name\n    code\n    __typename\n  }\n  section {\n    id\n    name\n    __typename\n  }\n  subsection {\n    id\n    __typename\n  }\n  showPicture\n  ...Kicker_data\n  ...LogoSet_data\n  ...Heading_data\n  ...Subheading_data\n  ...CollectionShareToolbar_share\n  ... on HasPromotionalProperties {\n    promotionalMedia {\n      ...HeaderImageFragment_promoImage\n      ... on EmbeddedInteractive {\n        id\n        promotionalMedia {\n          ...HeaderImageFragment_promoImage\n          __typename\n        }\n        __typename\n      }\n      ... on Video {\n        id\n        promotionalMedia {\n          ...HeaderImageFragment_promoImage\n          ... on Video {\n            id\n            promotionalMedia {\n              ...HeaderImageFragment_promoImage\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Audio {\n        id\n        promotionalMedia {\n          ...HeaderImageFragment_promoImage\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Kicker_data on LegacyCollection {\n  id\n  section {\n    id\n    displayName\n    url\n    __typename\n  }\n  subsection {\n    id\n    displayName\n    url\n    __typename\n  }\n  __typename\n}\n\nfragment LogoSet_data on LegacyCollection {\n  id\n  subsection {\n    id\n    name\n    __typename\n  }\n  __typename\n}\n\nfragment Heading_data on LegacyCollection {\n  id\n  name\n  slug\n  section {\n    id\n    displayName\n    __typename\n  }\n  __typename\n}\n\nfragment Subheading_data on LegacyCollection {\n  id\n  tagline\n  bylines {\n    creators {\n      ... on Person {\n        id\n        legacyData {\n          htmlBiography\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CollectionShareToolbar_share on LegacyCollection {\n  id\n  ...ShareToolbar_share\n  __typename\n}\n\nfragment ShareToolbar_share on CreativeWork {\n  headline {\n    default\n    __typename\n  }\n  summary\n  ... on Published {\n    url\n    __typename\n  }\n  commentProperties {\n    status\n    __typename\n  }\n  ...ShareButton_share\n  ...CommentCountContainer_article\n  __typename\n}\n\nfragment ShareButton_share on CreativeWork {\n  ...ShareMenu_share\n  __typename\n}\n\nfragment ShareMenu_share on CreativeWork {\n  headline {\n    default\n    __typename\n  }\n  summary\n  ... on Published {\n    url\n    __typename\n  }\n  __typename\n}\n\nfragment CommentCountContainer_article on Article {\n  id\n  commentProperties {\n    status\n    __typename\n  }\n  ...CommentCount_article\n  __typename\n}\n\nfragment CommentCount_article on CreativeWork {\n  ... on Published {\n    sourceId\n    url\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderImageFragment_promoImage on Image {\n  id\n  assetCrops: crops(\n    renditionNames: [\"thumbLarge\", \"thumbStandard\", \"articleLarge\", \"superJumbo\"]\n  ) {\n    name\n    renditions {\n      url\n      height\n      width\n      name\n      __typename\n    }\n    __typename\n  }\n  caption {\n    text\n    __typename\n  }\n  __typename\n}\n\nfragment SupplementalHeader_data on LegacyCollection {\n  id\n  groupings {\n    name\n    containers {\n      label\n      name\n      relations {\n        asset {\n          __typename\n          ... on Node {\n            id\n            __typename\n          }\n          ...EmbeddedInteractive_media\n          ...Capsule_data\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment EmbeddedInteractive_media on EmbeddedInteractive {\n  id\n  appName\n  storyFormat\n  slug\n  html\n  compatibility\n  ...EmbeddedInline_media\n  ...EmbeddedIframe_media\n  __typename\n}\n\nfragment EmbeddedInline_media on CreativeWork {\n  headline {\n    default\n    __typename\n  }\n  advertisingProperties {\n    sensitivity\n    __typename\n  }\n  displayProperties {\n    displayForPromotionOnly\n    displayOverrides\n    maxWidth: maximumWidth\n    minWidth: minimumWidth\n    __typename\n  }\n  bylines {\n    prefix\n    creators {\n      ... on TimesTag {\n        displayName\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ... on Published {\n    sourceId\n    __typename\n  }\n  ... on InteractiveWork {\n    credit\n    leadin\n    note\n    dataSource\n    html\n    __typename\n  }\n  ... on Interactive {\n    id\n    slug\n    __typename\n  }\n  ... on EmbeddedInteractive {\n    id\n    slug\n    __typename\n  }\n  __typename\n}\n\nfragment EmbeddedIframe_media on CreativeWork {\n  headline {\n    default\n    __typename\n  }\n  displayProperties {\n    displayForPromotionOnly\n    maxWidth: maximumWidth\n    __typename\n  }\n  ... on Interactive {\n    id\n    slug\n    __typename\n  }\n  ... on EmbeddedInteractive {\n    id\n    slug\n    __typename\n  }\n  ... on Published {\n    sourceId\n    uri\n    __typename\n  }\n  __typename\n}\n\nfragment Capsule_data on Capsule {\n  body {\n    ...DocumentBlock_data\n    __typename\n  }\n  __typename\n}\n\nfragment DocumentBlock_data on DocumentBlock {\n  content @filterEmpty {\n    __typename\n    ...AudioBlock_data\n    ...BlockquoteBlock_data\n    ...BylineBlock_data\n    ...CardDeckBlock_data\n    ...ClaimReviewBlock_data\n    ...DetailBlock_data\n    ...DiptychBlock_data\n    ...Dropzone_data\n    ...EmailSignupBlock_data\n    ...EditableRelatedLinksBlock_data\n    ...HeaderBasicBlock_data\n    ...HeaderLiveBriefingBlock_data\n    ...Heading1Block_data\n    ...Heading2Block_data\n    ...Heading3Block_data\n    ...GridBlock_data\n    ...ImageBlock_data\n    ...InstagramEmbedBlock_data\n    ...InteractiveBlock_data\n    ...HeaderLegacyBlock_data\n    ...LabelBlock_data\n    ...ListBlock_data\n    ...ParagraphBlock_data\n    ...LegacyTableBlock_data\n    ...PullquoteBlock_data\n    ...SlideshowBlock_data\n    ...SoundcloudEmbedBlock_data\n    ...SpotifyEmbedBlock_data\n    ...SummaryBlock_data\n    ...RuleBlock_data\n    ...StoryRelatedLinksBlock_data\n    ...TimestampBlock_data\n    ...TwitterEmbedBlock_data\n    ...UnstructuredBlock_data\n    ...VideoBlock_data\n    ...YouTubeEmbedBlock_data\n    ...HeaderFullBleedHorizontalBlock_data\n    ...HeaderMultimediaBlock_data\n    ... on HeaderFullBleedHorizontalBlock {\n      displayOverride\n      byline {\n        ...BylineBlock_data\n        ... on BylineBlock {\n          bylines {\n            prefix\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      timestampBlock {\n        ...TimestampBlock_data\n        __typename\n      }\n      __typename\n    }\n    ...HeaderFullBleedVerticalBlock_data\n    ... on HeaderFullBleedVerticalBlock {\n      displayOverride\n      alignment\n      byline @filterEmpty {\n        ...BylineBlock_data\n        ... on BylineBlock {\n          bylines {\n            prefix\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      timestampBlock {\n        ...TimestampBlock_data\n        __typename\n      }\n      __typename\n    }\n    ... on Dropzone {\n      adsDesktop\n      adsMobile\n      index\n      __typename\n    }\n    ... on BlockWithFallback {\n      fallback {\n        __typename\n        ...HeaderLegacyBlock_data\n        ...TextOnlyDocumentBlock_data\n      }\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment AudioBlock_data on AudioBlock {\n  media {\n    id\n    headline {\n      default\n      __typename\n    }\n    promotionalHeadline\n    length\n    sourceId\n    summary\n    podcastSeries {\n      title\n      summary\n      image {\n        id\n        crops(cropNames: [FLEXIBLE]) {\n          renditions {\n            url\n            name\n            width\n            height\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ...SpanAudio_media\n    __typename\n  }\n  __typename\n}\n\nfragment SpanAudio_media on Audio {\n  id\n  credit\n  headline {\n    default\n    __typename\n  }\n  summary\n  audioTranscript: transcript {\n    transcriptFragment {\n      text\n      speaker\n      timecode {\n        start\n        end\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  promotionalHeadline\n  fileUrl\n  length\n  podcastSeries {\n    name\n    __typename\n  }\n  section {\n    id\n    name\n    __typename\n  }\n  sourceId\n  __typename\n}\n\nfragment BlockquoteBlock_data on BlockquoteBlock {\n  content {\n    ...ParagraphBlock_data\n    __typename\n  }\n  __typename\n}\n\nfragment ParagraphBlock_data on ParagraphBlock {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment TextInline_content on InlineUnion {\n  __typename\n  ... on LineBreakInline {\n    type\n    __typename\n  }\n  ... on TextInline {\n    text\n    formats {\n      __typename\n      ... on BoldFormat {\n        type\n        __typename\n      }\n      ... on ItalicFormat {\n        type\n        __typename\n      }\n      ... on LinkFormat {\n        url\n        title\n        __typename\n      }\n    }\n    __typename\n  }\n}\n\nfragment BylineBlock_data on BylineBlock {\n  textAlign\n  hideHeadshots\n  bylines {\n    prefix\n    creators {\n      ... on Person {\n        id\n        displayName\n        bioUrl\n        promotionalMedia {\n          ... on Image {\n            id\n            crops(renditionNames: \"thumbLarge\") {\n              renditions {\n                url\n                name\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    renderedRepresentation\n    __typename\n  }\n  role @filterEmpty {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment CardDeckBlock_data on CardDeckBlock {\n  media {\n    id\n    ...onCardDeck\n    __typename\n  }\n  __typename\n}\n\nfragment onCardDeck on CardDeck {\n  __typename\n  id\n  uri\n  slug\n  sourceId\n  url\n  asset {\n    __typename\n    ... on Carousel {\n      data\n      cards {\n        key\n        data\n        assets {\n          ... on Published {\n            uri\n            url\n            sourceId\n            __typename\n          }\n          ... on Image {\n            id\n            credit\n            sourceId\n            altText\n            crops(\n              renditionNames: [\"videoSixteenByNine1050\", \"videoSixteenByNine600\", \"threeByTwoMediumAt2X\", \"verticalTwoByThree735\", \"square640\", \"threeByTwoMediumAt2X\"]\n            ) {\n              name\n              renditions {\n                name\n                url\n                width\n                height\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          ... on Video {\n            id\n            advertisingProperties {\n              sensitivity\n              __typename\n            }\n            bylines {\n              renderedRepresentation\n              __typename\n            }\n            transcript\n            duration\n            renditions {\n              aspectRatio\n              type\n              url\n              width\n              height\n              __typename\n            }\n            isCinemagraph\n            promotionalMedia {\n              ... on Image {\n                id\n                credit\n                crops(\n                  renditionNames: [\"videoSixteenByNine1050\", \"videoSixteenByNine600\", \"threeByTwoMediumAt2X\", \"verticalTwoByThree735\", \"square640\", \"threeByTwoMediumAt2X\", \"square640\"]\n                ) {\n                  name\n                  renditions {\n                    name\n                    url\n                    width\n                    height\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            summary\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n  }\n}\n\nfragment ClaimReviewBlock_data on ClaimReviewBlock {\n  alternateRating\n  claim\n  claimDate\n  claimReviewUrl\n  claimUrl\n  content {\n    ...TextInline_content\n    __typename\n  }\n  firstPublished\n  hideClaim\n  rating\n  source\n  __typename\n}\n\nfragment DetailBlock_data on DetailBlock {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment DiptychBlock_data on DiptychBlock {\n  size\n  imageOne {\n    id\n    ... on Image {\n      id\n      imageType\n      url\n      uri\n      credit\n      legacyHtmlCaption\n      altText\n      crops(\n        renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"popup\", \"mobileMasterAt3x\"]\n      ) {\n        renditions {\n          url\n          name\n          width\n          height\n          __typename\n        }\n        __typename\n      }\n      caption {\n        text\n        content {\n          ... on ParagraphBlock {\n            __typename\n            content {\n              ... on TextInline {\n                text\n                ...TextInline_content\n                __typename\n              }\n              __typename\n            }\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  imageTwo {\n    id\n    ... on Image {\n      id\n      imageType\n      url\n      uri\n      credit\n      legacyHtmlCaption\n      altText\n      crops(\n        renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"popup\", \"mobileMasterAt3x\"]\n      ) {\n        renditions {\n          url\n          name\n          width\n          height\n          __typename\n        }\n        __typename\n      }\n      caption {\n        text\n        content {\n          ... on ParagraphBlock {\n            __typename\n            content {\n              ... on TextInline {\n                text\n                ...TextInline_content\n                __typename\n              }\n              __typename\n            }\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Dropzone_data on Dropzone {\n  index\n  bad\n  adsMobile\n  adsDesktop\n  __typename\n}\n\nfragment EmailSignupBlock_data on EmailSignupBlock {\n  productCode\n  newsletterSummary: summary {\n    ... on TextInline {\n      text\n      __typename\n    }\n    __typename\n  }\n  newsletterHeading: heading {\n    ... on TextInline {\n      text\n      __typename\n    }\n    __typename\n  }\n  productDefaults {\n    title\n    caption\n    allowedEntitlement\n    subscriptionPageLink\n    isOnsiteFreeTrialEnabled\n    altText\n    frequency\n    caption\n    sampleUrl\n    thumbImg\n    __typename\n  }\n  __typename\n}\n\nfragment EditableRelatedLinksBlock_data on EditableRelatedLinksBlock {\n  linkCount\n  editableRelatedLinksDisplayStyle: displayStyle\n  header {\n    isDisplayed\n    title {\n      ...TextInline_content\n      __typename\n    }\n    description {\n      ...TextInline_content\n      __typename\n    }\n    __typename\n  }\n  writtenThruRelated {\n    kicker\n    related {\n      ...SharedRelatedLinkBlock_data\n      __typename\n    }\n    promotionalProperties {\n      media {\n        __typename\n      }\n      __typename\n    }\n    writeThruHeadline {\n      ...TextInline_content\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SharedRelatedLinkBlock_data on HasPromotionalProperties {\n  promotionalHeadline\n  promotionalSummary\n  ... on CreativeWork {\n    headline {\n      default\n      seo\n      __typename\n    }\n    summary\n    __typename\n  }\n  ... on Published {\n    url\n    firstPublished\n    __typename\n  }\n  ... on Promo {\n    id\n    targetUrl\n    __typename\n  }\n  ... on Article {\n    id\n    typeOfMaterials\n    collections(type: SPOTLIGHT) @filterEmpty {\n      mobileHeader\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  promotionalMedia {\n    ...SharedRelatedLinkBlock_promoImage\n    ... on Video {\n      id\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    ... on Audio {\n      id\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    ... on Slideshow {\n      id\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    ... on Interactive {\n      id\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    ... on EmbeddedInteractive {\n      id\n      promotionalMedia {\n        ...SharedRelatedLinkBlock_promoImage\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SharedRelatedLinkBlock_promoImage on Image {\n  id\n  credit\n  crops(\n    renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\", \"thumbLarge\"]\n  ) {\n    renditions {\n      url\n      name\n      width\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderMultimediaBlock_data on HeaderMultimediaBlock {\n  headlineColor\n  backgroundColor\n  headline {\n    ... on Heading1Block {\n      content {\n        ... on TextInline {\n          text\n          __typename\n        }\n        __typename\n      }\n      textAlign\n      __typename\n    }\n    __typename\n  }\n  summary {\n    content {\n      ... on TextInline {\n        text\n        __typename\n      }\n      __typename\n    }\n    textAlign\n    __typename\n  }\n  media {\n    ... on VideoBlock {\n      size\n      promotionalOverride {\n        ...HeaderMultimediaBlock_promoImage\n        ... on Video {\n          id\n          renditions {\n            width\n            height\n            bitrate\n            url\n            type\n            aspectRatio\n            __typename\n          }\n          promotionalMedia {\n            ...HeaderMultimediaBlock_promoImage\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      media {\n        id\n        promotionalMedia {\n          ...HeaderMultimediaBlock_promoImage\n          __typename\n        }\n        ... on Video {\n          url\n          duration\n          sourceId\n          productionType\n          advertisingProperties {\n            sensitivity\n            __typename\n          }\n          firstPublished\n          promotionalMedia {\n            ... on Video {\n              id\n              renditions {\n                width\n                height\n                bitrate\n                url\n                type\n                aspectRatio\n                __typename\n              }\n              promotionalMedia {\n                ...HeaderMultimediaBlock_promoImage\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          renditions {\n            width\n            height\n            bitrate\n            url\n            type\n            aspectRatio\n            __typename\n          }\n          videoTranscript: transcript\n          playlist {\n            videos(first: 4) {\n              ...Connection_pageInfo\n              edges @filterEmpty {\n                node {\n                  advertisingProperties {\n                    sensitivity\n                    sponsored\n                    __typename\n                  }\n                  id\n                  sourceId\n                  duration\n                  section {\n                    id\n                    name\n                    __typename\n                  }\n                  headline {\n                    default\n                    __typename\n                  }\n                  renditions {\n                    url\n                    type\n                    __typename\n                  }\n                  url\n                  promotionalMedia {\n                    ...HeaderMultimediaBlock_promoImage\n                    ... on Video {\n                      id\n                      promotionalMedia {\n                        ...HeaderMultimediaBlock_promoImage\n                        __typename\n                      }\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            id\n            promotionalHeadline\n            url\n            sourceId\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on AudioBlock {\n      media {\n        id\n        ... on Audio {\n          id\n          transcript {\n            __typename\n          }\n          id\n          headline {\n            default\n            __typename\n          }\n          summary\n          fileUrl\n          credit\n          firstPublished\n          length\n          subscribeUrls {\n            url\n            platform\n            __typename\n          }\n          promotionalMedia {\n            ... on Image {\n              id\n              crops(renditionNames: [\"jumbo\"]) {\n                renditions {\n                  url\n                  width\n                  height\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          podcastSeries {\n            title\n            subtitle\n            name\n            itunesUrl\n            image {\n              id\n              crops(\n                cropNames: [FIFTEEN_BY_SEVEN, THREE_BY_TWO, MASTER, MEDIUM_SQUARE, HORIZONTAL]\n                renditionNames: [\"videoLarge\", \"videoFifteenBySeven2610\", \"articleLarge\", \"square320\"]\n              ) {\n                name\n                renditions {\n                  width\n                  url\n                  name\n                  height\n                  format\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            collection {\n              id\n              ... on LegacyCollection {\n                name\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          transcript {\n            transcriptFragment {\n              text\n              speaker\n              timecode {\n                start\n                end\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderMultimediaBlock_promoImage on Image {\n  id\n  crops(\n    cropNames: [MEDIUM_SQUARE, THREE_BY_TWO, TWO_BY_THREE, SIXTEEN_BY_NINE, FIFTEEN_BY_SEVEN, MASTER]\n  ) {\n    name\n    renditions {\n      name\n      width\n      height\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderFullBleedHorizontalBlock_data on HeaderFullBleedHorizontalBlock {\n  headlineColor\n  displayOverride\n  gradientEnabled\n  label {\n    ...LabelBlock_data\n    __typename\n  }\n  headline {\n    ...Heading1Block_data\n    __typename\n  }\n  summary {\n    ...SummaryBlock_data\n    __typename\n  }\n  textPosition {\n    mobile\n    desktop\n    __typename\n  }\n  ledeMedia {\n    __typename\n    ... on ImageBlock {\n      size\n      media {\n        id\n        crops(\n          renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"mobileMasterAt3x\"]\n        ) {\n          bleed {\n            percentTop\n            percentLeft\n            percentRight\n            percentBottom\n            __typename\n          }\n          renditions {\n            url\n            name\n            width\n            height\n            __typename\n          }\n          __typename\n        }\n        legacyHtmlCaption\n        altText\n        credit\n        __typename\n      }\n      __typename\n    }\n    ... on VideoBlock {\n      media {\n        id\n        aspectRatio\n        renditions {\n          width\n          height\n          url\n          __typename\n        }\n        summary\n        bylines {\n          renderedRepresentation\n          __typename\n        }\n        promotionalMedia {\n          ... on Image {\n            id\n            crops {\n              name\n              renditions {\n                width\n                height\n                url\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          ... on Video {\n            id\n            promotionalMedia {\n              ... on Image {\n                id\n                crops {\n                  name\n                  renditions {\n                    width\n                    height\n                    url\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment Heading1Block_data on Heading1Block {\n  textAlign\n  content {\n    ... on InlineUnion {\n      __typename\n      ... on LineBreakInline {\n        type\n        __typename\n      }\n      ... on TextInline {\n        text @stripHtml\n        formats {\n          __typename\n          ... on BoldFormat {\n            type\n            __typename\n          }\n          ... on ItalicFormat {\n            type\n            __typename\n          }\n          ... on LinkFormat {\n            url\n            title\n            __typename\n          }\n        }\n        __typename\n      }\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment LabelBlock_data on LabelBlock {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment SummaryBlock_data on SummaryBlock {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderFullBleedVerticalBlock_data on HeaderFullBleedVerticalBlock {\n  headlineColor\n  backgroundColor\n  displayOverride\n  alignment\n  label {\n    ...LabelBlock_data\n    __typename\n  }\n  headline {\n    ...Heading1Block_data\n    __typename\n  }\n  summary {\n    ...SummaryBlock_data\n    __typename\n  }\n  textPosition {\n    mobile\n    desktop\n    __typename\n  }\n  ledeMedia {\n    __typename\n    ... on ImageBlock {\n      size\n      media {\n        id\n        crops(\n          renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"mobileMasterAt3x\"]\n        ) {\n          bleed {\n            percentTop\n            percentLeft\n            percentRight\n            percentBottom\n            __typename\n          }\n          renditions {\n            url\n            name\n            width\n            height\n            __typename\n          }\n          __typename\n        }\n        legacyHtmlCaption\n        altText\n        credit\n        __typename\n      }\n      __typename\n    }\n    ... on VideoBlock {\n      media {\n        id\n        summary\n        aspectRatio\n        renditions {\n          width\n          height\n          url\n          __typename\n        }\n        bylines {\n          renderedRepresentation\n          __typename\n        }\n        promotionalMedia {\n          ... on Image {\n            id\n            crops {\n              name\n              renditions {\n                width\n                height\n                url\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          ... on Video {\n            id\n            promotionalMedia {\n              ... on Image {\n                id\n                crops {\n                  name\n                  renditions {\n                    width\n                    height\n                    url\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment HeaderLegacyBlock_data on HeaderLegacyBlock {\n  subhead {\n    ...Heading2Block_data\n    __typename\n  }\n  label {\n    ...LabelBlock_data\n    __typename\n  }\n  headline {\n    ...Heading1Block_data\n    __typename\n  }\n  ledeMedia {\n    __typename\n    ... on ImageBlock {\n      size\n      __typename\n    }\n    ...ImageBlock_data\n    ...VideoBlock_data\n    ...InteractiveBlock_data\n    ...SlideshowBlock_data\n  }\n  byline {\n    ...BylineBlock_data\n    ... on BylineBlock {\n      bylines {\n        prefix\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  timestampBlock {\n    ...TimestampBlock_data\n    __typename\n  }\n  __typename\n}\n\nfragment InteractiveBlock_data on InteractiveBlock {\n  media {\n    __typename\n    ...EmbeddedInteractive_media\n    ... on EmbeddedInteractive {\n      id\n      displayProperties {\n        maximumWidth\n        minimumWidth\n        __typename\n      }\n      __typename\n    }\n    ... on HasPromotionalProperties {\n      promotionalMedia {\n        __typename\n        ...SpanImage_media\n        ... on HasPromotionalProperties {\n          promotionalMedia {\n            ...SpanImage_media\n            __typename\n          }\n          __typename\n        }\n      }\n      __typename\n    }\n    ... on Interactive {\n      id\n      headline {\n        default\n        __typename\n      }\n      url\n      summary\n      firstPublished\n      sourceApplication\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment SpanImage_media on Image {\n  id\n  caption {\n    text @stripHtml\n    __typename\n  }\n  spanImageCrops: crops(\n    renditionNames: [\"videoLarge\", \"largeHorizontalJumbo\", \"articleLarge\", \"master1050\", \"square640\", \"thumbLarge\", \"threeByTwoSmallAt2X\", \"threeByTwoMediumAt2X\", \"threeByTwoLargeAt2X\"]\n  ) {\n    name\n    renditions {\n      name\n      url\n      width\n      height\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SlideshowBlock_data on SlideshowBlock {\n  size\n  media {\n    id\n    displayProperties {\n      template\n      __typename\n    }\n    promotionalMedia {\n      ... on Image {\n        id\n        credit\n        url\n        slideshowCrops: crops(renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\"]) {\n          renditions {\n            url\n            width\n            height\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    url\n    headline {\n      default\n      __typename\n    }\n    summary\n    slides {\n      ...SlideshowEmbedded_data\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SlideshowEmbedded_data on SlideshowSlide {\n  legacyHtmlCaption\n  image {\n    id\n    credit\n    summary\n    uri\n    crops(cropNames: [MASTER, THREE_BY_TWO, MOBILE_MASTER]) {\n      name\n      renditions {\n        url\n        name\n        width\n        height\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Heading2Block_data on Heading2Block {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment ImageBlock_data on ImageBlock {\n  size\n  media {\n    id\n    imageType\n    url\n    uri\n    credit\n    legacyHtmlCaption\n    crops(\n      renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"articleInline\", \"popup\", \"mobileMasterAt3x\"]\n    ) {\n      renditions {\n        url\n        name\n        width\n        height\n        __typename\n      }\n      __typename\n    }\n    caption {\n      text\n      content {\n        ... on ParagraphBlock {\n          __typename\n          content {\n            ... on TextInline {\n              text\n              ...TextInline_content\n              __typename\n            }\n            __typename\n          }\n        }\n        __typename\n      }\n      __typename\n    }\n    altText\n    __typename\n  }\n  __typename\n}\n\nfragment VideoBlock_data on VideoBlock {\n  size\n  autoplay\n  muted\n  hideControls\n  hideSummary\n  looping\n  controls\n  media {\n    id\n    summary\n    firstPublished\n    aspectRatio\n    transcript\n    productionType\n    promotionalMedia {\n      ... on Image {\n        id\n        credit\n        __typename\n      }\n      __typename\n    }\n    advertisingProperties {\n      sensitivity\n      sponsored\n      __typename\n    }\n    ...SpanVideo_media\n    __typename\n  }\n  promotionalOverride {\n    ...Video_promoVideo\n    ...Video_promoImage\n    __typename\n  }\n  __typename\n}\n\nfragment SpanVideo_media on Video {\n  id\n  transcript\n  advertisingProperties {\n    sensitivity\n    __typename\n  }\n  aspectRatio\n  bylines {\n    renderedRepresentation\n    __typename\n  }\n  contentSeries\n  cues {\n    name\n    type\n    timeIn\n    timeOut\n    __typename\n  }\n  duration\n  embedded\n  headline {\n    default\n    __typename\n  }\n  is360\n  isLive\n  isCinemagraph\n  liveUrls\n  playlist {\n    videos(first: 4) {\n      edges @filterEmpty {\n        node {\n          advertisingProperties {\n            sensitivity\n            sponsored\n            __typename\n          }\n          id\n          sourceId\n          duration\n          section {\n            id\n            name\n            __typename\n          }\n          headline {\n            default\n            __typename\n          }\n          renditions {\n            url\n            type\n            __typename\n          }\n          url\n          promotionalMedia {\n            ... on Node {\n              id\n              __typename\n            }\n            ... on Image {\n              id\n              crops(renditionNames: [\"videoSixteenByNine540\"]) {\n                name\n                renditions {\n                  name\n                  height\n                  width\n                  url\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    id\n    promotionalHeadline\n    url\n    sourceId\n    __typename\n  }\n  promotionalHeadline\n  promotionalMedia {\n    ...Video_promoImage\n    __typename\n  }\n  promotionalSummary\n  related @filterEmpty {\n    ... on Article {\n      id\n      promotionalHeadline\n      url\n      sourceId\n      __typename\n    }\n    __typename\n  }\n  renditions {\n    width\n    url\n    type\n    height\n    bitrate\n    aspectRatio\n    __typename\n  }\n  section {\n    id\n    name\n    displayName\n    __typename\n  }\n  shortUrl\n  sourceId\n  subsection {\n    id\n    name\n    __typename\n  }\n  summary\n  timesTags @filterEmpty {\n    __typename\n    displayName\n    isAdvertisingBrandSensitive\n    vernacular\n  }\n  url\n  ... on Video {\n    id\n    url\n    duration\n    sourceId\n    promotionalMedia {\n      ...Video_promoVideo\n      __typename\n    }\n    renditions {\n      width\n      height\n      bitrate\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Video_promoVideo on Video {\n  id\n  renditions {\n    width\n    height\n    bitrate\n    url\n    __typename\n  }\n  promotionalMedia {\n    ... on Node {\n      id\n      __typename\n    }\n    ...Video_promoImage\n    __typename\n  }\n  __typename\n}\n\nfragment Video_promoImage on Image {\n  id\n  crops(\n    renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"videoLarge\", \"videoSixteenByNine1050\", \"videoSixteenByNine3000\", \"square640\", \"verticalTwoByThree735\", \"threeByTwoSmallAt2X\", \"threeByTwoMediumAt2X\", \"threeByTwoLargeAt2X\"]\n  ) {\n    name\n    renditions {\n      name\n      width\n      height\n      url\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment TimestampBlock_data on TimestampBlock {\n  timestamp\n  align\n  showUpdatedTimestamp\n  __typename\n}\n\nfragment HeaderBasicBlock_data on HeaderBasicBlock {\n  label {\n    ...LabelBlock_data\n    __typename\n  }\n  headline {\n    ...Heading1Block_data\n    __typename\n  }\n  summary {\n    ...SummaryBlock_data\n    __typename\n  }\n  ledeMedia {\n    __typename\n    ...ImageBlock_data\n    ...VideoBlock_data\n    ...SlideshowBlock_data\n    ...InteractiveBlock_data\n  }\n  byline {\n    ...BylineBlock_data\n    ... on BylineBlock {\n      bylines {\n        prefix\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  summary {\n    ...SummaryBlock_data\n    __typename\n  }\n  timestampBlock {\n    ...TimestampBlock_data\n    showUpdatedTimestamp\n    __typename\n  }\n  __typename\n}\n\nfragment HeaderLiveBriefingBlock_data on HeaderLiveBriefingBlock {\n  label {\n    ...LabelBlock_data\n    __typename\n  }\n  headline {\n    ...Heading1Block_data\n    __typename\n  }\n  summary {\n    ...SummaryBlock_data\n    __typename\n  }\n  byline {\n    ...BylineBlock_data\n    ... on BylineBlock {\n      bylines {\n        prefix\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  latestUpdate {\n    label\n    content {\n      ...TextInline_content\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Heading3Block_data on Heading3Block {\n  textAlign\n  content {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment GridBlock_data on GridBlock {\n  columnsMobile\n  gutterMobile\n  columnsDesktop\n  gutterDesktop\n  size\n  caption\n  credit\n  gridMedia: media {\n    id\n    ... on Image {\n      __typename\n      id\n      imageType\n      url\n      uri\n      credit\n      legacyHtmlCaption\n      altText\n      crops(\n        renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"popup\", \"square320\", \"mobileMasterAt3x\"]\n      ) {\n        name\n        renditions {\n          url\n          name\n          width\n          height\n          __typename\n        }\n        __typename\n      }\n      caption {\n        text\n        __typename\n      }\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment InstagramEmbedBlock_data on InstagramEmbedBlock {\n  instagramUrl\n  __typename\n}\n\nfragment ListBlock_data on ListBlock {\n  style\n  content {\n    __typename\n    ...ListItemBlock_data\n  }\n  __typename\n}\n\nfragment ListItemBlock_data on ListItemBlock {\n  content {\n    __typename\n    ...ParagraphBlock_data\n  }\n  __typename\n}\n\nfragment LegacyTableBlock_data on LegacyTableBlock {\n  legacyTableHtml: html\n  __typename\n}\n\nfragment PullquoteBlock_data on PullquoteBlock {\n  quote {\n    ...TextInline_content\n    __typename\n  }\n  attribution {\n    ...TextInline_content\n    __typename\n  }\n  __typename\n}\n\nfragment SoundcloudEmbedBlock_data on SoundcloudEmbedBlock {\n  soundcloudUrl\n  html\n  __typename\n}\n\nfragment SpotifyEmbedBlock_data on SpotifyEmbedBlock {\n  spotifyEmbedUrl\n  spotifyPlayerStyle: playerStyle\n  __typename\n}\n\nfragment RuleBlock_data on RuleBlock {\n  type\n  __typename\n}\n\nfragment StoryRelatedLinksBlock_data on RelatedLinksBlock {\n  ...SharedRelatedLinksBlock_data\n  related @filterEmpty {\n    ... on CreativeWork {\n      __typename\n      section {\n        id\n        displayName\n        __typename\n      }\n    }\n    ... on Article {\n      id\n      bylines {\n        creators {\n          ... on Person {\n            id\n            displayName\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SharedRelatedLinksBlock_data on RelatedLinksBlock {\n  displayStyle: displayStyle\n  title {\n    ...TextInline_content\n    __typename\n  }\n  description {\n    ...TextInline_content\n    __typename\n  }\n  related @filterEmpty {\n    __typename\n    ...SharedRelatedLinkBlock_data\n  }\n  __typename\n}\n\nfragment TwitterEmbedBlock_data on TwitterEmbedBlock {\n  twitterUrl\n  snapshot\n  hideMedia\n  html\n  __typename\n}\n\nfragment UnstructuredBlock_data on UnstructuredBlock {\n  dataType\n  data\n  mediaRefs: media {\n    __typename\n    ... on Published {\n      uri\n      __typename\n    }\n    ... on CreativeWork {\n      headline {\n        default\n        __typename\n      }\n      section {\n        id\n        displayName\n        __typename\n      }\n      __typename\n    }\n    ... on HasPromotionalProperties {\n      promotionalHeadline\n      promotionalSummary\n      ... on Published {\n        url\n        firstPublished\n        __typename\n      }\n      promotionalMedia {\n        ... on Image {\n          id\n          crops(\n            renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\"]\n          ) {\n            name\n            renditions {\n              url\n              name\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        ... on Video {\n          id\n          promotionalMedia {\n            ... on Image {\n              id\n              crops(\n                renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\"]\n              ) {\n                name\n                renditions {\n                  url\n                  name\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        ... on Slideshow {\n          id\n          promotionalMedia {\n            ... on Image {\n              id\n              crops(\n                renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\"]\n              ) {\n                name\n                renditions {\n                  url\n                  name\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        ... on Interactive {\n          id\n          promotionalMedia {\n            ... on Image {\n              id\n              crops(\n                renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\"]\n              ) {\n                name\n                renditions {\n                  url\n                  name\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        ... on EmbeddedInteractive {\n          id\n          promotionalMedia {\n            ... on Image {\n              id\n              crops(\n                renditionNames: [\"threeByTwoSmallAt2X\", \"videoLarge\", \"mediumThreeByTwo440\"]\n              ) {\n                name\n                renditions {\n                  url\n                  name\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Article {\n        id\n        bylines {\n          creators {\n            ... on Person {\n              id\n              displayName\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    ... on Image {\n      __typename\n      id\n      imageType\n      url\n      uri\n      credit\n      legacyHtmlCaption\n      altText\n      crops(\n        renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"popup\", \"square320\", \"mobileMasterAt3x\"]\n      ) {\n        name\n        renditions {\n          url\n          name\n          width\n          height\n          __typename\n        }\n        __typename\n      }\n      caption {\n        text\n        __typename\n      }\n    }\n    ... on Video {\n      id\n      __typename\n      url\n      uri\n      duration\n      sourceId\n      headline {\n        default\n        __typename\n      }\n      summary\n      renditions {\n        width\n        height\n        bitrate\n        url\n        type\n        __typename\n      }\n    }\n  }\n  __typename\n}\n\nfragment YouTubeEmbedBlock_data on YouTubeEmbedBlock {\n  youTubeId\n  caption\n  credit\n  __typename\n}\n\nfragment TextOnlyDocumentBlock_data on TextOnlyDocumentBlock {\n  content {\n    __typename\n    ...ParagraphBlock_data\n  }\n  __typename\n}\n\nfragment StorylinesHub_data on LegacyCollection {\n  id\n  __typename\n  storylines {\n    storyline {\n      hubAssets {\n        asset {\n          ... on Published {\n            uri\n            url\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...LiveUpdatesBlock_data\n  ...HeadingBlock_collection\n  ...HubBlock_data\n}\n\nfragment HeadingBlock_collection on LegacyCollection {\n  id\n  name\n  url\n  shortUrl\n  tagline\n  longDescription\n  ...ShareToolbar_share\n  __typename\n}\n\nfragment LiveUpdatesBlock_data on CreativeWork {\n  ... on Published {\n    uri\n    __typename\n  }\n  storylines {\n    storyline {\n      promotedLiveAssets {\n        displayName\n        asset {\n          __typename\n          ... on Published {\n            lastModified\n            __typename\n          }\n          ... on Article {\n            id\n            url\n            body @filterEmpty {\n              content {\n                __typename\n                ... on Heading2Block {\n                  content {\n                    __typename\n                    ... on TextInline {\n                      text\n                      __typename\n                    }\n                  }\n                  __typename\n                }\n              }\n              __typename\n            }\n            __typename\n          }\n          ... on FeedPublication {\n            id\n            items_beta(first: 7) {\n              ...Connection_pageInfo\n              edges {\n                node {\n                  ...HubLiveUpdates_items\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          ... on LegacyCollection {\n            id\n            url\n            sourceId\n            stream(exclusionMode: NONE, first: 7) {\n              ...Connection_pageInfo\n              edges {\n                node {\n                  ...HubLiveUpdates_items\n                  ... on Article {\n                    id\n                    promotionalMedia {\n                      ... on Image {\n                        id\n                        credit\n                        __typename\n                      }\n                      ...SpanImage_media\n                      ...SpanVideo_media\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            ...getPromotionalMediaFromLiveAsset_promoMedia\n            __typename\n          }\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment HubLiveUpdates_items on Article {\n  id\n  sourceId\n  url\n  headline {\n    default\n    sentence\n    __typename\n  }\n  __typename\n}\n\nfragment getPromotionalMediaFromLiveAsset_image on Image {\n  id\n  crops(\n    renditionNames: [\"articleLarge\", \"jumbo\", \"superJumbo\", \"threeByTwoLargeAt2X\"]\n  ) {\n    name\n    renditions {\n      url\n      name\n      __typename\n    }\n    __typename\n  }\n  credit\n  caption {\n    text\n    __typename\n  }\n  __typename\n}\n\nfragment getPromotionalMediaFromLiveAsset_promoMedia on LegacyCollection {\n  id\n  groupings {\n    name\n    containers {\n      name\n      relations {\n        asset {\n          __typename\n          ... on Capsule {\n            sourceId\n            ... on HasPromotionalProperties {\n              promotionalMedia {\n                __typename\n                ... on Image {\n                  id\n                  ...getPromotionalMediaFromLiveAsset_image\n                  __typename\n                }\n              }\n              __typename\n            }\n            body {\n              content {\n                ... on HeaderBasicBlock {\n                  ledeMedia {\n                    ... on ImageBlock {\n                      size\n                      media {\n                        id\n                        ...getPromotionalMediaFromLiveAsset_image\n                        __typename\n                      }\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment HubBlock_data on LegacyCollection {\n  id\n  active\n  storylines {\n    storyline {\n      ...TopLinks_data\n      __typename\n    }\n    __typename\n  }\n  ...LiveUpdatesBlock_data\n  ...LedeBlock_data\n  __typename\n}\n\nfragment TopLinks_data on Storyline {\n  url\n  displayName\n  primaryAssets {\n    displayName\n    asset {\n      headline {\n        default\n        __typename\n      }\n      ... on Published {\n        url\n        __typename\n      }\n      ... on HasPromotionalProperties {\n        promotionalMedia {\n          ...PromoImage_data\n          ... on Video {\n            id\n            promotionalMedia {\n              ...PromoImage_data\n              __typename\n            }\n            __typename\n          }\n          ... on Interactive {\n            id\n            promotionalMedia {\n              ...PromoImage_data\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment PromoImage_data on Image {\n  id\n  spanImageCrops: crops(renditionNames: [\"thumbLarge\"]) {\n    name\n    renditions {\n      name\n      url\n      width\n      height\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment LedeBlock_data on CreativeWork {\n  storylines {\n    storyline {\n      experimentalJsonBlob\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Rank_data on LegacyCollection {\n  id\n  slug\n  groupings {\n    name\n    containers {\n      name\n      template\n      relations {\n        __typename\n      }\n      ...Groupings_data\n      ...EmbeddedCollection_container\n      __typename\n    }\n    __typename\n  }\n  ...SupplementalRank_data\n  __typename\n}\n\nfragment EmbeddedCollection_container on LegacyCollectionContainer {\n  label\n  relations {\n    overrides\n    __typename\n  }\n  __typename\n}\n\nfragment Groupings_data on LegacyCollectionContainer {\n  label @stripHtml\n  relations {\n    overrides\n    asset {\n      ...ShowcaseStory_data\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SupplementalRank_data on LegacyCollection {\n  id\n  groupings {\n    name\n    containers {\n      name\n      relations {\n        asset {\n          __typename\n          ... on Node {\n            id\n            __typename\n          }\n          ...Capsule_data\n          ...EmbeddedInteractive_media\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Rank_page on LegacyCollectionsPage {\n  ...EmbeddedCollection_page\n  __typename\n}\n\nfragment EmbeddedCollection_page on LegacyCollectionsPage {\n  embeddedCollections {\n    label\n    overrides\n    template\n    collection {\n      collectionType\n      id\n      name\n      url\n      slug\n      __typename\n    }\n    stream {\n      ...Connection_pageInfo\n      edges {\n        node @filterEmpty {\n          ... on Node {\n            id\n            __typename\n          }\n          ...DefaultAsset_data\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment DefaultAsset_data on HasPromotionalProperties {\n  ... on Published {\n    url\n    lastMajorModification\n    __typename\n  }\n  ... on Promo {\n    id\n    targetUrl\n    promotionalHeadline\n    promotionalSummary\n    __typename\n  }\n  ... on CreativeWork {\n    summary\n    headline {\n      default\n      __typename\n    }\n    kicker\n    column {\n      id\n      name\n      __typename\n    }\n    bylines {\n      prefix\n      creators {\n        ... on Person {\n          id\n          displayName\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...Image_data\n  __typename\n}\n\nfragment Rank_highlights on LegacyCollection {\n  id\n  highlights(first: 20) {\n    ...Highlights_data\n    __typename\n  }\n  __typename\n}\n\nfragment Highlights_data on AssetsConnection {\n  ...Connection_pageInfo\n  edges {\n    node {\n      __typename\n      ... on Node {\n        id\n        __typename\n      }\n      ...ShowcaseStory_data\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Supplemental_data on LegacyCollection {\n  id\n  ...SimpleStream_data\n  ...SupplementalModules_data\n  __typename\n}\n\nfragment SimpleStream_data on LegacyCollection {\n  id\n  collectionsPage {\n    stream(\n      first: $first\n      after: $cursor\n      query: $collectionQuery\n      exclusionMode: $exclusionMode\n    ) {\n      ...AssetStream_stream\n      pageInfo {\n        hasNextPage\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment AssetStream_stream on AssetsConnection {\n  ...Connection_pageInfo\n  edges @filterEmpty {\n    node {\n      __typename\n      ...StreamAsset_asset\n    }\n    __typename\n  }\n  pageInfo {\n    hasNextPage\n    endCursor\n    __typename\n  }\n  totalCount\n  __typename\n}\n\nfragment StreamAsset_asset on Node {\n  id\n  ... on Published {\n    url\n    firstPublished\n    __typename\n  }\n  ... on Article {\n    typeOfMaterials\n    archiveProperties {\n      lede\n      __typename\n    }\n    __typename\n  }\n  ... on CreativeWork {\n    headline {\n      default\n      __typename\n    }\n    bylines {\n      renderedRepresentation\n      prefix\n      creators: creatorSnapshots {\n        ... on PersonSnapshot {\n          displayName\n          url\n          promotionalMedia {\n            ... on Image {\n              id\n              crops {\n                renditions {\n                  url\n                  name\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    kicker\n    summary\n    __typename\n  }\n  ... on HasPromotionalProperties {\n    promotionalMedia {\n      __typename\n      ... on Image {\n        id\n        ...Stream_image\n        __typename\n      }\n      ... on Video {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            ...Stream_image\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Audio {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            ...Stream_image\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Slideshow {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            ...Stream_image\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on Interactive {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            ...Stream_image\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on EmbeddedInteractive {\n        id\n        promotionalMedia {\n          ... on Image {\n            id\n            ...Stream_image\n            __typename\n          }\n          ...Stream_image\n          __typename\n        }\n        __typename\n      }\n    }\n    __typename\n  }\n  ... on Video {\n    embedded\n    __typename\n  }\n  ... on Slideshow {\n    displayProperties {\n      template\n      __typename\n    }\n    __typename\n  }\n  ... on Article {\n    translations {\n      ...TranslationLinks_translations\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Stream_image on Image {\n  id\n  crops(cropNames: [THREE_BY_TWO]) {\n    name\n    renditions {\n      width\n      url\n      name\n      height\n      __typename\n    }\n    __typename\n  }\n  timesTags {\n    vernacular\n    __typename\n  }\n  __typename\n}\n\nfragment TranslationLinks_translations on ArticleTranslation {\n  url\n  linkText\n  translatedLinkText\n  language {\n    code\n    __typename\n  }\n  __typename\n}\n\nfragment SupplementalModules_data on LegacyCollection {\n  id\n  ...Freeform_collection\n  slug\n  name\n  bylines {\n    creators {\n      ... on Person {\n        id\n        ...EmailAuthor_data\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  socialMedia {\n    ...SocialMedia_data\n    __typename\n  }\n  groupings {\n    name\n    containers {\n      name\n      relations {\n        asset {\n          __typename\n          ... on EmbeddedInteractive {\n            id\n            slug\n            displayProperties {\n              displayForPromotionOnly\n              __typename\n            }\n            headline {\n              default\n              __typename\n            }\n            ...EmbeddedInteractive_media\n            ...Freeform_asset\n            __typename\n          }\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment Freeform_collection on LegacyCollection {\n  id\n  slug\n  __typename\n}\n\nfragment Freeform_asset on EmbeddedInteractive {\n  id\n  headline {\n    default\n    __typename\n  }\n  displayProperties {\n    displayForPromotionOnly\n    __typename\n  }\n  html\n  __typename\n}\n\nfragment EmailAuthor_data on Person {\n  id\n  displayName\n  publiclyEmailable\n  __typename\n}\n\nfragment SocialMedia_data on ContactDetailsSocialMedia {\n  type\n  account\n  __typename\n}\n\nfragment StorylinesMenu_legacyCollection on LegacyCollection {\n  id\n  ...StorylineMenuBlock_creativeWork\n  ...Region_legacyCollection\n  __typename\n}\n\nfragment StorylineMenuBlock_creativeWork on CreativeWork {\n  storylines {\n    testName\n    ruleName\n    storyline {\n      uri\n      url\n      tone\n      displayName\n      hubAssets {\n        asset {\n          ...Asset_storyline\n          __typename\n        }\n        __typename\n      }\n      primaryAssets {\n        displayName\n        status\n        asset {\n          ...Asset_storyline\n          ... on LegacyCollection {\n            id\n            active\n            lastModified\n            __typename\n          }\n          ... on FeedPublication {\n            id\n            live\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...Asset_storyline\n  __typename\n}\n\nfragment Asset_storyline on CreativeWork {\n  ... on Published {\n    uri\n    url\n    __typename\n  }\n  __typename\n}\n\nfragment Region_legacyCollection on LegacyCollection {\n  id\n  associatedAssets {\n    region\n    assetName\n    ruleName\n    testName\n    parentTest\n    asset {\n      __typename\n      ... on EmbeddedInteractive {\n        id\n        html\n        slug\n        compatibility\n        displayProperties {\n          minimumWidth\n          maximumWidth\n          displayOverrides\n          __typename\n        }\n        __typename\n      }\n      ... on Capsule {\n        uri\n        __typename\n      }\n    }\n    __typename\n  }\n  __typename\n}\n",
        "variables": {
            "cursor": "YXJyYXljb25uZWN0aW9uOjk=",
            "exclusionMode": "HIGHLIGHTS_AND_EMBEDDED",
            "first": 10,
            "hasHighlightsList": False,
            "highlightsListFirst": 0,
            "highlightsListUri": "nyt://per/personalized-list/__null__",
            "id": path,
            "isHighEnd": False,
            "streamQuery": {
                "sort": "newest"
            }
        },
        "extensions": {
            "persistedQuery": {
                "sha256Hash": "140d05c45d7333667c1370196e17f7bd9684776be586b6ca817f900ee7dbb76b",
                "version": 1
            }
        }
    }
    # sha256Hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "nyt-app-type": "project-vi",
        "nyt-app-version": "0.0.5",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/pxQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oyui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCuc5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"114\", \"Microsoft Edge\";v=\"114\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.51",
        "x-nyt-internal-meter-override": "undefined"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', json_data=data, headers=headers)
    if not gql_json:
        return None
    return gql_json


def get_live_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    dt = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(pytz.timezone('US/Eastern'))
    paths[1] = dt.strftime('%Y')
    paths[2] = dt.strftime('%m')
    paths[3] = dt.strftime('%d')
    path = '/' + '/'.join(paths)
    url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, path)
    print(path)
    data = {
        "operationName": "LiveBlogQuery",
        "variables": {
            "collectionUrl": path,
            "previewUris":[],
            "blogItemSocialPostId": "nyt://",
            "reporterUpdateSocialPostId": "nyt://",
            "first": 15,
            "additionalFirst": 38,
            "id": url,
            "after": "YXJyYXljb25uZWN0aW9uOjE0",
            "before": "",
            "last": "",
            "additionalAfter": "YXJyYXljb25uZWN0aW9uOjEw",
            "additionalBefore": "",
            "additionalLast": ""
        },
        "extensions": {"persistedQuery": {            "version":1,"sha256Hash":"a4f3f780bebcd7ea613dfe4fd44c06639f371f7bab3c5f4efd15741e205c0193"
            }
        }
    }
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "nyt-app-type": "project-vi",
        "nyt-app-version": "0.0.5",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/pxQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oyui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCuc5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', data=json.dumps(data), headers=headers)
    if not gql_json:
        return None
    return gql_json


def get_feed(url, args, site_json, save_debug=False):
    if '/live/' in args['url']:
        collection = get_live_feed(url, args, site_json, save_debug)
        if save_debug:
            utils.write_file(collection, './debug/feed.json')
        return None

    feed = None
    if args['url'].endswith('.xml') or args['url'].endswith('/feed/'):
        feed = rss.get_feed(url, args, site_json, save_debug, get_content)
        m = re.search(r'publish/https://www\.nytimes\.com/(.*)/rss\.xml', args['url'])
        if m:
            path = m.group(1)
        else:
            path = ''
    else:
        split_url = urlsplit(url)
        path = split_url.path
        feed = utils.init_jsonfeed(args)

    if path:
        collection = get_collection(path)
        if collection:
            if save_debug:
                utils.write_file(collection, './debug/feed.json')
            highlights = collection['data']['legacyCollection']['highlights']['edges']
            streams = collection['data']['legacyCollection']['collectionsPage']['stream']['edges']
            for edge in highlights + streams:
                if edge['node'].get('url'):
                    url = edge['node']['url']
                elif edge['node'].get('targetUrl'):
                    url = edge['node']['targetUrl']
                else:
                    continue
                if not next((it for it in feed['items'] if it['url'] == url), None):
                    if save_debug:
                        logger.debug('getting content for ' + url)
                    item = get_content(url, args, site_json, save_debug)
                    if item:
                        if utils.filter_item(item, args) == True:
                            feed['items'].append(item)
        feed['items'] = sorted(feed['items'], key=lambda i: i['_timestamp'], reverse=True)

    return feed