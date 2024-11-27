import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_content(block, images):
    start_tag = ''
    end_tag = ''
    if block['type'] == 'text':
        return block['data'].strip()
    elif block['type'] == 'a':
        start_tag = '<a href="{}">'.format(block['attribs']['href'])
        end_tag = '</a>'
    elif block['type'] == 'div':
        pass
    elif block['type'] == 'br' or block['type'] == 'hr':
        return '<{}/>'.format(block['type'])
    elif block['type'] == 'img':
        image = None
        if images:
            image = next((it for it in images if it['url'] == block['attribs']['src']), None)
        if image and image.get('size_1200x800'):
            return utils.add_image(image['size_1200x800']['url'], image.get('title'))
        else:
            return utils.add_image(block['attribs']['src'], block['attribs'].get('title'))
    elif block['type'] == 'iframe':
        return utils.add_embed(block['attribs']['src'])
    elif block['type'] == 'blockquote':
        if block.get('attribs') and block['attribs'].get('class'):
            if re.search(r'twitter-tweet', block['attribs']['class']):
                block_html = ''
                for child in block['children']:
                    block_html += render_content(child, images)
                m = re.findall(r'https://twitter\.com/[^/]+/status/\d+', block_html)
                return utils.add_embed(m[-1])
            else:
                logger.warning('unhandled blockquote class ' + block['attribs']['class'])
                start_tag = '<blockquote>'
                end_tag = '</blockquote>'
        else:
            start_tag = '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
            end_tag = '</blockquote>'
    elif block['type'] == 'blockquote-quote':
        quote = render_content(block['children'][0], images)
        if len(block['children']) > 1:
            author = render_content(block['children'][1], images)
        else:
            author = ''
        return utils.add_pullquote(quote, author)
    elif block['type'] == 'h3':
        for child in block['children']:
            if child['type'] == 'a' and child['attribs'].get('data-entity-bundle') and child['attribs']['data-entity-bundle'] == 'article':
                return ''
        start_tag = '<h3>'
        end_tag = '</h3>'
    elif block['type'] == 'script':
        return ''
    else:
        if not re.search(r'^(em|h\d|li|p|ol|strong|u|ul)$', block['type']):
            logger.debug('unknown block type ' + block['type'])
        start_tag = '<{}>'.format(block['type'])
        end_tag = '</{}>'.format(block['type'])

    block_html = start_tag
    if block.get('children'):
        for child in block['children']:
            block_html += render_content(child, images)
    block_html += end_tag
    return block_html

def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'multimedia.scmp.com':
        # https://multimedia.scmp.com/widgets/business/bitcoin/bitcoin.html
        # https://multimedia.scmp.com/2019/graphics/launchers/20230130.html
        return None

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "apikey": site_json['apikey'],
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"112\", \"Microsoft Edge\";v=\"112\", \"Not:A-Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }

    json_data = {}
    json_data['operationName'] = 'getarticlebyid'
    json_data['variables'] = {
        "entityId": paths[-2],
        "applicationId": site_json['applicationId']
    }
    json_data['query'] = 'query getarticlebyid($entityUuid: String, $entityId: String, $applicationId: String!, $customContents: [CustomContent], $withBeijingOplympicsOgImage: Boolean = false, $withHongKong25OgImage: Boolean = false) {\n  paid:article(filter:{entityUuid: $entityUuid}) {\n    entityId\n    contentLock\n  }\n  content(contentType:Article, filter:{entityUuid: $entityUuid, entityId: $entityId, applicationId: $applicationId}) {\n    ... on Article {\n      __typename\n      sentiment\n      longCredit\n      authorLocations\n      entityId\n      entityUuid\n      hasVideoContent\n      doNotOpenInApp\n      disableOffPlatformContent\n      knowledgeQuestion\n      youtubeSmartEmbed\n      types {\n        entityId\n        entityUuid\n        name\n        urlAlias\n        description\n      }\n      tmpLiveArticle {\n        status\n      }\n      relatedColumnArticles {\n        entityId\n        headline\n        socialHeadline\n        urlAlias\n        types {\n          entityId\n          entityUuid\n          name\n          urlAlias\n        }\n        authors {\n          entityUuid\n          entityId\n          types\n          name\n          image(filter: {type: AUTHOR_IMAGE}) {\n            title\n            type\n            url\n            size_118x118: style(filter: {style: "118x118"}) {\n              url\n            }\n          }\n          urlAlias\n        }\n      }\n      corrections {\n        correction (format: HTML)\n        timestamp\n      }\n      headline\n      multimediaEmbed(format: JSON)\n      flag\n      identity\n      printHeadline\n      subHeadline\n      socialHeadline\n      summary\n      keywords\n      urlAlias\n      sourceUrl\n      shortURL\n      displaySlideShow\n      updatedDate\n      createdDate\n      paywallTypes {\n        entityId\n        entityUuid\n        name\n      }\n      publishedDate\n      published\n      advertZone(version: 2)\n      sponsorType\n      contentLock\n      commentCount\n      writer\n      copyrighted\n      topics {\n        disableFollow\n        entityUuid\n        entityId\n        name\n        urlAlias\n        types\n        sponsor {\n          name\n          type\n          entityUuid\n          entityId\n          images {\n            title\n            url\n          }\n          description\n        }\n        mobileImage: image(filter: {type: MOBILE_APP_IMAGE}) {\n          url\n          title\n          size_118x118: style(filter: {style: "118x118"}) {\n            url\n          }\n        }\n        relatedNewsletters {\n          entityId\n          entityUuid\n          name\n          alternativeName\n          description(format: TEXT)\n          summary(format: TEXT)\n        }\n        reverseSectionTopics {\n          images {\n            url\n            type\n          }\n          metatags {\n            key\n            value\n          }\n          types\n          urlAlias\n          name\n          entityId\n        }\n      }\n      articleVideos(filter:{type:"youtube", source:"SCMP"}) {\n        videoId\n      }\n      body(customContents: $customContents)\n      sections {\n        entityUuid\n        advertZone\n        entityId\n        name\n        urlAlias (checkRedirect: true)\n        relatedNewsletterIds\n        relatedNewsletters {\n          entityId\n          entityUuid\n          name\n          alternativeName\n          description(format: TEXT)\n          summary(format: TEXT)\n        }\n        images {\n          url\n          type\n        }\n        metatags {\n          key\n          value\n        }\n      }\n      authors {\n        entityUuid\n        entityId\n        types\n        name\n        location\n        role\n        image(filter: {type: AUTHOR_IMAGE}) {\n          title\n          type\n          url\n          size_118x118: style(filter: {style: "118x118"}) {\n            url\n          }\n        }\n        socialLinks {\n          class\n          title\n          url\n        }\n        authorLarge: image(filter: {type: AUTHOR_LARGE}) {\n          title\n          type\n          url\n          size_118x118: style(filter: {style: "118x118"}) {\n            url\n          }\n        }\n        urlAlias\n        position\n        bio\n        followCount\n        disableFollow\n      }\n      coverImages: images(filter: {type: {values: COVER}}) {\n        title\n        type\n        url\n        size_landscape_250_99: style(filter: {style: "landscape_250_99"}) {\n          url\n        }\n      }\n      coverMobileImages: images(filter: {type: {values: COVER_MOBILE}}) {\n        title\n        type\n        url\n      }\n      heroImages: images(filter: {type: {values: HERO}}) {\n        title\n        type\n        url\n      }\n      images {\n        title\n        url\n        isSlideshow\n        type\n        width\n        height\n        size_1200x800: style(filter: {style: "1200x800"}) {\n          url\n        }\n        size_118x118: style(filter: {style: "118x118"}) {\n          url\n        }\n        size_1920x1080: style(filter: {style: "1920x1080"}) {\n          url\n        }\n        size_160x90: style(filter: {style: "160x90"}) {\n          url\n        }\n        size_144x81: style(filter: {style: "144x81"}) {\n          url\n        }\n        size_120x80: style(filter: {style: "120x80"}) {\n          url\n        }\n        size_768x768: style(filter: {style: "768x768"}) {\n          url\n        }\n        size_64x64: style(filter: {style: "64x64"}) {\n          url\n        }\n        size_237x147: style(filter: {style: "237x147"}) {\n          url\n        }\n        size_652x446: style(filter: {style: "652x446"}) {\n          url\n        }\n        size_landscape_250_99: style(filter: {style: "landscape_250_99"}) {\n          url\n        }\n        ogCoronavirusGeneric: style(filter: {style: "og_image_scmp_coronavirus_generic"}) {\n          url: path\n        }\n        ogCoronavirusOpinion: style(filter: {style: "og_image_scmp_coronavirus_opinion"}) {\n          url: path\n        }\n        ogCoronavirusLive: style(filter: {style: "og_image_scmp_coronavirus_live"}) {\n          url: path\n        }\n        ogBeijingOlympicsGeneric: style( filter: { style: "beijing_olympic_2022_generic" }) @include(if: $withBeijingOplympicsOgImage) {\n          url\n        }\n        ogBeijingOlympicsOpinion: style( filter: { style: "beijing_olympic_2022_opinion" }) @include(if: $withBeijingOplympicsOgImage) {\n          url\n        }\n        ogBeijingOlympicsLive: style( filter: { style: "beijing_olympic_2022_live" }) @include(if: $withBeijingOplympicsOgImage) {\n          url\n        }\n        ogHongKong25Generic: style( filter: { style: "og_image_scmp_hk25" }) @include(if: $withHongKong25OgImage) {\n          url: path\n        }\n        ogHongKong25Opinion: style( filter: { style: "og_image_scmp_hk25_opinion" }) @include(if: $withHongKong25OgImage) {\n          url: path\n        }\n        ogHongKong25Live: style( filter: { style: "og_image_scmp_hk25_live" }) @include(if: $withHongKong25OgImage) {\n          url: path\n        }\n        ogAnalysis: style(filter: {style: "og_image_scmp_analysis"}) {\n          url: path\n        }\n        ogEditorial: style(filter: {style: "og_image_scmp_editorial"}) {\n          url: path\n        }\n        ogExplainer: style(filter: {style: "og_image_scmp_explainer"}) {\n          url: path\n        }\n        ogFactCheck: style(filter: {style: "og_image_scmp_fact_check"}) {\n          url: path\n        }\n        ogLive: style(filter: {style: "og_image_scmp_live"}) {\n          url: path\n        }\n        ogObituary: style(filter: {style: "og_image_scmp_obituary"}) {\n          url: path\n        }\n        ogOpinion: style(filter: {style: "og_image_scmp_opinion"}) {\n          url: path\n        }\n        ogReview: style(filter: {style: "og_image_scmp_review"}) {\n          url: path\n        }\n        ogDebate: style(filter: {style: "og_image_scmp_debate"}) {\n          url: path\n        }\n        ogGeneric: style(filter: {style: "og_image_scmp_generic"}) {\n          url: path\n        }\n        ogSeries: style(filter: {style: "og_image_scmp_series"}) {\n          url: path\n        }\n        twitterCoronavirusGeneric: style(filter: {style: "og_twitter_scmp_coronavirus_generic"}) {\n          url\n        }\n        twitterCoronavirusOpinion: style(filter: {style: "og_twitter_scmp_coronavirus_opinion"}) {\n          url\n        }\n        twitterCoronavirusLive: style(filter: {style: "og_twitter_scmp_coronavirus_live"}) {\n          url\n        }\n        twitterAnalysis: style(filter: {style: "og_twitter_scmp_analysis"}) {\n          url\n        }\n        twitterExplainer: style(filter: {style: "og_twitter_scmp_explainer"}) {\n          url\n        }\n        twitterEditorial: style(filter: {style: "og_twitter_scmp_editorial"}) {\n          url\n        }\n        twitterFactCheck: style(filter: {style: "og_twitter_scmp_fact_check"}) {\n          url\n        }\n        twitterLive: style(filter: {style: "og_twitter_scmp_live"}) {\n          url\n        }\n        twitterObituary: style(filter: {style: "og_twitter_scmp_obituary"}) {\n          url\n        }\n        twitterOpinion: style(filter: {style: "og_twitter_scmp_opinion"}) {\n          url\n        }\n        twitterDebate: style(filter: {style: "og_twitter_scmp_debate"}) {\n          url\n        }\n        twitterReview: style(filter: {style: "og_twitter_scmp_review"}) {\n          url\n        }\n        twitterGeneric: style(filter: {style: "og_twitter_scmp_generic"}) {\n          url\n        }\n        twitterSeries: style(filter: {style: "og_twitter_scmp_series"}) {\n          url\n        }\n      }\n      relatedNewsletters {\n        entityId\n        entityUuid\n        name\n        alternativeName\n        description(format: TEXT)\n        summary(format: TEXT)\n      }\n      moreOnThisArticles {\n        sponsorType\n        entityId\n        entityUuid\n        headline\n        socialHeadline\n        images {\n          url\n          size_237x147: style(filter: {style: "237x147"}) {\n            url\n          }\n        }\n        urlAlias\n        updatedDate\n        publishedDate\n        types {\n          entityId\n        }\n      }\n      relatedLinks\n    }\n  }\n}\n'
    gql_json = utils.post_url('https://apigw.scmp.com/content-delivery/v1', json_data=json_data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    content_json = gql_json['data']['content']

    item = {}
    item['id'] = content_json['entityId']
    item['url'] = '{}:{}{}'.format(split_url.scheme, split_url.netloc, content_json['urlAlias'])
    item['title'] = content_json['headline']

    # Offset to match date/time in ld+json info
    dt = datetime.fromtimestamp(content_json['publishedDate']/1000 + 4*3600).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(content_json['updatedDate']/1000 + 4*3600).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in content_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if content_json.get('keywords'):
        for it in content_json['keywords']:
            item['tags'] += list(map(str.strip, it.split(',')))
    if content_json.get('topics'):
        for it in content_json['topics']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if content_json.get('summary'):
        item['summary'] = ''
        for block in content_json['summary']:
            item['summary'] += render_content(block, None)

    item['content_html'] = ''
    if content_json.get('subHeadline'):
        for block in content_json['subHeadline']:
            item['content_html'] += render_content(block, None)

    lede = False
    if content_json.get('multimediaEmbed') and content_json['multimediaEmbed'][0].get('attribs') and content_json['multimediaEmbed'][0]['attribs'].get('class') and 'hero-video' in content_json['multimediaEmbed'][0]['attribs']['class']:
        lede = True
        for block in content_json['multimediaEmbed'][0]['children']:
            item['content_html'] += render_content(block, None)

    if content_json.get('images'):
        images = content_json['images']
        for it in images:
            if it['type']:
                if it['type'] == 'default':
                    if it.get('size_1200x800'):
                        item['image'] = it['size_1200x800']['url']
                    else:
                        item['image'] = it['url']
                elif it['type'] == 'leading':
                    caption = it.get('title')
                    if it.get('size_1200x800'):
                        img_src = it['size_1200x800']['url']
                    else:
                        img_src = it['url']
                    if not lede:
                        item['content_html'] += utils.add_image(img_src, caption)
                    if not item.get('image'):
                        item['image'] = img_src
    else:
        images = None

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    for block in content_json['body']:
        item['content_html'] += render_content(block, images)

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.scmp.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
