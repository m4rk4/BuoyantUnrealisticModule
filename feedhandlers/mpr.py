import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def render_content(content_list):
    content_html = ''
    for content in content_list:
        if content['type'] == 'text':
            start_tag = ''
            end_tag = ''
            if content.get('marks'):
                for mark in content['marks']:
                    if mark['type'] == 'em' or mark['type'] == 'strong':
                        start_tag += '<{}>'.format(mark['type'])
                        end_tag = '</{}>'.format(mark['type']) + end_tag
                    elif mark['type'] == 'link':
                        start_tag += '<a href="{}">'.format(mark['attrs']['href'])
                        end_tag = '</a>' + end_tag
                    else:
                        logger.warning('unhandled mark type ' + mark['type'])
            content_html += start_tag + content['text'] + end_tag
        elif content['type'] == 'paragraph':
            if content.get('content'):
                content_html += '<p>' + render_content(content['content']) + '</p>'
            else:
                content_html += '<p></p>'
        elif content['type'] == 'heading':
            content_html += '<h{0}>{1}</h{0}>'.format(content['attrs']['level'], render_content(content['content']))
        elif content['type'] == 'apm_image':
            captions = []
            if content['attrs'].get('long_caption'):
                captions.append(content['attrs']['long_caption'])
            elif content['attrs'].get('short_caption'):
                captions.append(content['attrs']['short_caption'])
            if content['attrs'].get('credit'):
                captions.append(content['attrs']['credit'])
            img_src = ''
            if content['attrs'].get('aspect_ratios'):
                if content['attrs']['aspect_ratios'].get(content['attrs']['preferred_aspect_ratio_slug']) and content['attrs']['aspect_ratios'][content['attrs']['preferred_aspect_ratio_slug']].get('instances'):
                    it = utils.closest_dict(content['attrs']['aspect_ratios'][content['attrs']['preferred_aspect_ratio_slug']]['instances'], 'width', 1200)
                    img_src = it['url']
                elif content['attrs']['aspect_ratios'].get('normal') and content_html['attrs']['aspect_ratios']['normal'].get('instances'):
                    it = utils.closest_dict(content['attrs']['aspect_ratios']['normal']['instances'], 'width', 1200)
                    img_src = it['url']
            if not img_src:
                img_src = content['attrs']['url']
            content_html += utils.add_image(img_src, ' | '.join(captions))
        elif content['type'] == 'apm_gallery':
            if content['attrs'].get('title') and content['attrs']['title'].strip():
                content_html += '<h3>' + content['attrs']['title'].strip() + '</h3>'
            content_html += render_content(content['content'])
        elif content['type'] == 'apm_custom_html':
            if re.search(r'(dwcdn\.net|instagram\.com|reddit\.com|twitter\.com|x\.com)/', content['attrs']['fallback_url']):
                content_html += utils.add_embed(content['attrs']['fallback_url'])
            else:
                soup = BeautifulSoup(content['attrs']['html'], 'html.parser')
                if soup.iframe and soup.iframe.get('src'):
                    content_html += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled apm_custom_html content for ' + content['attrs']['fallback_url'])
        elif content['type'] == 'horizontal_rule':
            content_html += '<hr/>'
        elif content['type'] == 'bullet_list' or content['type'] == 'apm_related_list':
            content_html += '<ul>' + render_content(content['content']) + '</ul>'
        elif content['type'] == 'list_item':
            li = re.sub(r'^<p>(.*)</p>$', r'\1', render_content(content['content'])).replace('</p><p>', '<br/><br/>')
            content_html += '<li>' + li + '</li>'
        elif content['type'] == 'apm_related_link':
            content_html += '<li>'
            if content['attrs'].get('prefix'):
                content_html += '<strong>{}</strong> '.format(content['attrs']['prefix'])
            content_html += '<a href="{}">{}</a></li>'.format(content['attrs']['url'], content['attrs']['title'])
        else:
            logger.warning('unhandled content type ' + content['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if '/story/' in split_url.path:
        gql_query = {
            "operationName": "story",
            "variables": {
                "contentAreaSlug": site_json['contentAreaSlug'],
                "slug": split_url.path[7:]
            },
            "query": "query story($contentAreaSlug: String!, $slug: String!, $previewToken: String) {\n  story: story(\n    contentAreaSlug: $contentAreaSlug\n    slug: $slug\n    previewToken: $previewToken\n  ) {\n    id\n    title\n    shortTitle\n    subtitle\n    originalSourceUrl\n    supportedOutputFormats\n    resourceType\n    dateline\n    canonicalSlug\n    primaryCollection {\n      id\n      title\n      canonicalSlug\n      resourceType\n      templateName\n      results(pageSize: 4) {\n        items {\n          subtitle\n          title\n          resourceType\n          canonicalSlug\n          canonicalUrl\n          publishDate\n          collectionRelatedLinks {\n            url\n            title\n            prefix\n          }\n        }\n      }\n    }\n    collections {\n      rssUrl\n      canonicalSlug\n    }\n    contributors {\n      profile {\n        id\n        title\n        canonicalSlug\n      }\n      roles {\n        name\n      }\n      order\n    }\n    publishDate\n    updatedAt\n    body\n    description\n    descriptionText\n    resourceType\n    primaryAudio {\n      title\n      credit\n      durationHms\n      durationMs\n      transcriptText\n      transcripts {\n        mediaType\n        formatSlug\n        url\n      }\n      encodings {\n        format\n        mediaType\n        httpFilePath\n        filename\n        playFilePath\n      }\n    }\n    embeddedAssets {\n      audio\n      attachments\n      images\n      oembeds\n    }\n    primaryVisuals {\n      video {\n        url\n        caption\n        background\n        credit {\n          name\n          url\n        }\n      }\n      social {\n        aspect_ratios: aspectRatios {\n          uncropped {\n            instances {\n              url\n              width\n              height\n            }\n          }\n          widescreen {\n            instances {\n              url\n              width\n              height\n            }\n          }\n        }\n        fallback\n      }\n      lead {\n        preferredAspectRatio {\n          instances {\n            url\n            width\n            height\n          }\n        }\n        aspect_ratios: aspectRatios {\n          uncropped {\n            instances {\n              url\n              width\n              height\n            }\n          }\n          widescreen {\n            instances {\n              url\n              width\n              height\n            }\n          }\n          square {\n            instances {\n              url\n              width\n              height\n            }\n          }\n        }\n        contentArea\n        credit {\n          name\n          url\n        }\n        dateTaken\n        dateline\n        fallback\n        longCaption\n        rights {\n          redistributable\n        }\n        shortCaption\n        xid\n      }\n    }\n  }\n  alertConfig: potlatch(slug: \"mprnews/info-alert\") {\n    slug\n    json\n  }\n  blacklist: potlatch(slug: \"mprnews/related-stories-blacklist\") {\n    json\n  }\n  viafoura: potlatch(slug: \"mprnews/viafoura\") {\n    json\n  }\n  livechat: potlatch(slug: \"mprnews/viafoura-livechat\") {\n    json\n  }\n  donateAsk: potlatch(slug: \"mprnews/donate-ask-config\") {\n    json\n  }\n}\n"
        }
        gql_json = utils.post_url('https://cmsapi.publicradio.org/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/debug.json')
        story_json = gql_json['data']['story']
    elif '/episode/' in split_url.path:
        gql_query = {
            "operationName": "episode",
        "variables": {
            "contentAreaSlug": site_json['contentAreaSlug'],
            "slug": split_url.path[9:]
        },
        "query": "query episode($contentAreaSlug: String!, $slug: String!, $previewToken: String) {\n  episode: episode(\n    contentAreaSlug: $contentAreaSlug\n    slug: $slug\n    previewToken: $previewToken\n  ) {\n    id\n    title\n    subtitle\n    originalSourceUrl\n    canonicalSlug\n    supportedOutputFormats\n    primaryCollection {\n      id\n      title\n      canonicalSlug\n      templateName\n    }\n    collections {\n      rssUrl\n      canonicalSlug\n    }\n    contributors {\n      profile {\n        id\n        firstName\n        lastName\n        canonicalSlug\n      }\n      roles {\n        name\n      }\n    }\n    publishDate\n    updatedAt\n    body\n    description\n    descriptionText\n    resourceType\n    primaryAudio {\n      id\n      title\n      credit\n      durationHms\n      durationMs\n      transcriptText\n      transcripts {\n        mediaType\n        formatSlug\n        url\n      }\n      encodings {\n        format\n        mediaType\n        httpFilePath\n        filename\n        playFilePath\n      }\n    }\n    embeddedAssets {\n      audio\n      attachments\n      images\n      oembeds\n    }\n    primaryVisuals {\n      video {\n        url\n        caption\n        background\n        credit {\n          name\n          url\n        }\n      }\n      social {\n        aspect_ratios: aspectRatios {\n          uncropped {\n            instances {\n              url\n              width\n              height\n            }\n          }\n          widescreen {\n            instances {\n              url\n              width\n              height\n            }\n          }\n        }\n        fallback\n      }\n      lead {\n        preferredAspectRatio {\n          instances {\n            url\n            width\n            height\n          }\n        }\n        aspect_ratios: aspectRatios {\n          uncropped {\n            instances {\n              url\n              width\n              height\n            }\n          }\n          square {\n            instances {\n              url\n              width\n              height\n            }\n          }\n        }\n        contentArea\n        credit {\n          name\n          url\n        }\n        dateTaken\n        dateline\n        fallback\n        longCaption\n        shortCaption\n        xid\n      }\n    }\n  }\n  alertConfig: potlatch(slug: \"mprnews/info-alert\") {\n    slug\n    json\n  }\n  donateAsk: potlatch(slug: \"mprnews/donate-ask-config\") {\n    json\n  }\n}\n"
        }
        gql_json = utils.post_url('https://cmsapi.publicradio.org/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/debug.json')
        story_json = gql_json['data']['episode']
    else:
        if split_url.netloc == 'features.mprnews.org':
            item = {}
            item['url'] = url
            item['_image'] = '{}/screenshot?url={}&locator=%23htmlwidget_container'.format(config.server, quote_plus(item['url']))
            caption = '<a href="{}">View on MPR News</a>'.format(item['url'])
            item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
            return item

        logger.warning('unhandled url ' + url)
        return None

    item = {}
    item['id'] = story_json['id']
    item['url'] = 'https://{}/{}'.format(split_url.netloc, story_json['canonicalSlug'])
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['publishDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['updatedAt']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in story_json['contributors']:
        if it['profile'].get('lastName'):
            authors.append('{} {}'.format(it['profile']['firstName'], it['profile']['lastName']))
        elif it['profile'].get('title'):
            authors.append(it['profile']['title'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if story_json.get('collections'):
        item['tags'] = []
        for c in story_json['collections']:
            if c['canonicalSlug'].strip() and c['canonicalSlug'] != 'homepage':
                for it in c['canonicalSlug'].split('/'):
                    tag = it.replace('-', ' ')
                    if tag not in item['tags']:
                        item['tags'].append(tag)
        if len(item['tags']) == 0:
            del item['tags']

    if story_json.get('descriptionText'):
        item['summary'] = story_json['descriptionText']

    item['content_html'] = ''
    if story_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(story_json['subtitle'])

    if story_json.get('primaryVisuals') and story_json['primaryVisuals'].get('lead'):
        captions = []
        if story_json['primaryVisuals']['lead'].get('longCaption'):
            captions.append(story_json['primaryVisuals']['lead']['longCaption'])
        elif story_json['primaryVisuals']['lead'].get('shortCaption'):
            captions.append(story_json['primaryVisuals']['lead']['shortCaption'])
        if story_json['primaryVisuals']['lead'].get('credit'):
            captions.append(story_json['primaryVisuals']['lead']['credit']['name'])
        if story_json['primaryVisuals']['lead'].get('preferredAspectRatio') and story_json['primaryVisuals']['lead']['preferredAspectRatio'].get('instances'):
            it = utils.closest_dict(story_json['primaryVisuals']['lead']['preferredAspectRatio']['instances'], 'width', 1200)
            item['_image'] = it['url']
        elif story_json['primaryVisuals']['lead'].get('aspect_ratios') and story_json['primaryVisuals']['lead']['aspect_ratios'].get('uncropped') and story_json['primaryVisuals']['lead']['aspect_ratios']['uncropped'].get('instances'):
            it = utils.closest_dict(story_json['primaryVisuals']['lead']['aspect_ratios']['uncropped']['instances'], 'width', 1200)
            item['_image'] = it['url']
        elif story_json['primaryVisuals']['lead'].get('aspect_ratios') and story_json['primaryVisuals']['lead']['aspect_ratios'].get('normal') and story_json['primaryVisuals']['lead']['aspect_ratios']['normal'].get('instances'):
            it = utils.closest_dict(story_json['primaryVisuals']['lead']['aspect_ratios']['normal']['instances'], 'width', 1200)
            item['_image'] = it['url']
        else:
            item['_image'] = story_json['primaryVisuals']['lead']['fallback']
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if story_json.get('primaryAudio') and story_json['primaryAudio'].get('encodings'):
        audio = next((it for it in story_json['primaryAudio']['encodings'] if it['format'] == 'mp3'), None)
        if not audio:
            audio = story_json['primaryAudio']['encodings'][0]
        item['_audio'] = utils.get_redirect_url(audio['playFilePath'].replace('%user_agent', 'web'))
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = audio['mediaType']
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span style="padding-left:8px;"><a href="{0}">Listen:</a> <em>{2}</em></span></div>'.format(item['_audio'], config.server, story_json['primaryAudio']['title'])

    body_json = json.loads(story_json['body'])
    if save_debug:
        utils.write_file(body_json, './debug/content.json')

    item['content_html'] += render_content(body_json['content'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if len(paths) > 0:
        next_url += '?slug=' + '&slug='.join(paths)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if page_html:
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


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    feed_title = ''
    if len(paths) == 0:
        gql_query = {
            "operationName": "home",
            "variables": {
                "contentAreaSlug": site_json['contentAreaSlug'],
                "slug": "homepage"
            },
            "query": "query home($contentAreaSlug: String!, $slug: String!) {\n  homeList: collection(contentAreaSlug: $contentAreaSlug, slug: $slug) {\n    id\n    title\n    description\n    descriptionText\n    results(page: 1, pageSize: 20) {\n      items {\n        id\n        title\n        canonicalSlug\n        resourceType\n        description\n        descriptionText\n        primaryVisuals {\n          video {\n            url\n            caption\n            background\n            credit {\n              name\n              url\n            }\n          }\n          thumbnail {\n            preferredAspectRatio {\n              instances {\n                url\n                width\n                height\n              }\n            }\n            aspect_ratios: aspectRatios {\n              thumbnail {\n                instances {\n                  width\n                  height\n                  url\n                }\n              }\n              widescreen {\n                instances {\n                  width\n                  height\n                  url\n                }\n              }\n              uncropped {\n                instances {\n                  url\n                  width\n                  height\n                }\n              }\n              normal {\n                instances {\n                  url\n                  width\n                  height\n                }\n              }\n            }\n            contentArea\n            dateTaken\n            dateline\n            fallback\n            longCaption\n            shortCaption\n            xid\n          }\n          lead {\n            preferredAspectRatio {\n              instances {\n                url\n                width\n                height\n              }\n            }\n            aspect_ratios: aspectRatios {\n              thumbnail {\n                instances {\n                  width\n                  height\n                  url\n                }\n              }\n              widescreen {\n                instances {\n                  width\n                  height\n                  url\n                }\n              }\n              uncropped {\n                instances {\n                  url\n                  width\n                  height\n                }\n              }\n              normal {\n                instances {\n                  url\n                  width\n                  height\n                }\n              }\n            }\n            contentArea\n            dateTaken\n            dateline\n            fallback\n            longCaption\n            shortCaption\n            xid\n          }\n        }\n        audio {\n          id\n          title\n          durationHms\n          encodings {\n            httpFilePath\n            playFilePath\n            filename\n            durationMs\n          }\n        }\n        collectionRelatedLinks {\n          url\n          title\n          prefix\n        }\n        ... on Link {\n          destination\n        }\n      }\n    }\n  }\n  sidebar: collection(contentAreaSlug: $contentAreaSlug, slug: \"sidebar\") {\n    id\n    results(page: 1, pageSize: 4) {\n      items {\n        id\n        canonicalSlug\n        resourceType\n        title\n        descriptionText\n        ... on Link {\n          destination\n        }\n        ... on Collection {\n          results(page: 1, pageSize: 1) {\n            items {\n              title\n              resourceType\n              canonicalSlug\n            }\n          }\n        }\n      }\n    }\n  }\n  updraft: collection(\n    contentAreaSlug: $contentAreaSlug\n    slug: \"weather-and-climate/updraft\"\n  ) {\n    id\n    results(page: 1, pageSize: 1) {\n      items {\n        id\n        title\n        resourceType\n        canonicalSlug\n      }\n    }\n  }\n  electionPositionConfig: potlatch(slug: \"mprnews/local-election-display\") {\n    slug\n    json\n  }\n  alertConfig: potlatch(slug: \"mprnews/info-alert\") {\n    slug\n    json\n  }\n  homeStoryConfig: potlatch(slug: \"mprnews/homepage-stories\") {\n    slug\n    json\n  }\n  electionConfig: potlatch(slug: \"mprnews/election-widget-2020\") {\n    slug\n    json\n  }\n  racesConfig: potlatch(slug: \"mprnews/election-control\") {\n    slug\n    json\n  }\n  radarConfig: potlatch(slug: \"mprnews/homepage-radar\") {\n    slug\n    json\n  }\n}\n"
        }
        gql_json = utils.post_url('https://cmsapi.publicradio.org/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        stories = gql_json['data']['homeList']['results']['items']
    elif len(paths) > 0:
        gql_query = {
            "operationName": "collection",
            "variables": {
                "contentAreaSlug": site_json['contentAreaSlug'],
                "slug": '/'.join(paths)
            },
            "query": "query collection(\n  $contentAreaSlug: String!\n  $slug: String!\n  $pageNum: Int\n  $pageSize: Int\n) {\n  collection: collection(contentAreaSlug: $contentAreaSlug, slug: $slug) {\n    id\n    title\n    body\n    descriptionText\n    resourceType\n    embeddedAssetJson\n    canonicalSlug\n    contributors {\n      profile {\n        id\n        canonicalSlug\n        firstName\n        lastName\n        profileRelatedLinks {\n          uri\n          text\n          subtype\n        }\n      }\n    }\n    results(page: $pageNum, pageSize: $pageSize) {\n      nextPage\n      pageSize\n      totalPages\n      totalItems\n      previousPage\n      currentPage\n      items {\n        id\n        title\n        publishDate\n        description\n        descriptionText\n        canonicalSlug\n        resourceType\n        contributors {\n          profile {\n            id\n            firstName\n            lastName\n          }\n        }\n        collectionRelatedLinks {\n          url\n          title\n          prefix\n        }\n        ... on Link {\n          destination\n        }\n      }\n    }\n  }\n  weatherConfig: potlatch(slug: \"mprnews/weather-order\") {\n    slug\n    json\n  }\n  donateAsk: potlatch(slug: \"mprnews/donate-ask-config\") {\n    json\n  }\n}\n"
        }
        gql_json = utils.post_url('https://cmsapi.publicradio.org/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        stories = gql_json['data']['collection']['results']['items']
        feed_title = gql_json['data']['collection']['title']
    else:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        stories = next_data['pageProps']['data']['collection']['results']['items']

    n = 0
    feed_items = []
    for story in stories:
        story_url = 'https://{}/{}/{}'.format(split_url.netloc, story['resourceType'], story['canonicalSlug'])
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed