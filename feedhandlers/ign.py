import json, re
import curl_cffi
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_datetime(date):
    if date.endswith('Z'):
        date = date.replace('Z', '+00:00')
    elif date.endswith('+0000'):
        date = date.replace('+0000', '+00:00')
    return datetime.fromisoformat(date)


def get_api_data(post_data):
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "apollographql-client-name": "kraken",
        "apollographql-client-version": "v0.97.11",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache"
    }
    r = curl_cffi.post('https://mollusk.apis.ign.com/graphql', json=post_data, headers=headers, impersonate="chrome", proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('status code ' + str(r.status_code) + ' getting https://mollusk.apis.ign.com/graphql')
        utils.write_file(r.text, './debug/ign.txt')
        return None
    return r.json()


def get_catalog_by_id(catalog_id):
    post_data = {
        "operationName": "CatalogById",
        "variables": {
            "id": catalog_id
        },
        "query": "fragment catalogFields on Catalog {\n  content {\n    id\n    slug\n    title\n    state\n    updatedAt\n  }\n  items {\n    id\n    title\n    description\n    brand\n    model\n    large\n    regionCode\n    upVotes\n    caption\n    image {\n      url\n    }\n    object {\n      id\n      url\n      primaryReview {\n        id\n        score\n        articleUrl\n        videoUrl\n      }\n    }\n    links {\n      id\n      url\n      vendor\n      price\n      msrp\n      couponCode\n      amazonApsAsin\n      amazonApsNcakey\n    }\n    sponsorship {\n      ...sponsorshipFields\n    }\n  }\n}\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nquery CatalogById($id: ID!) {\n  catalogById(id: $id) {\n    ...catalogFields\n  }\n}\n"
    }
    return get_api_data(post_data)


def add_catalog_item(catalog_item, margin='1em auto'):
    card_image = '<div style="width:100%; height:100%; background:url(\'' + catalog_item['image']['url'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 0;"></div>'
    card_content = ''
    if catalog_item.get('caption'):
        card_content += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center; font-size:0.8em;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">' + catalog_item['caption'] + '</span></div>'
    card_content += '<div style="font-weight:bold; text-align:center;">' + catalog_item['title'] + '</div>'
    if catalog_item.get('description'):
        card_content += '<div style="margin-top:1em; font-size:smaller; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;">' + catalog_item['description'] + '</div>'
    footer_html = ''
    for it in catalog_item['links']:
        if it.get('price'):
            caption = '$' + str(it['price'])
        else:
            caption = 'See it'
        caption += ' at ' + it['vendor']
        if it.get('couponCode'):
            caption += '<br>(use code ' + it['couponCode'] + ')'
        footer_html += utils.add_button(it['url'], caption)
    return utils.format_small_card(card_image, card_content, footer_html, image_size='128px', content_style='padding:8px;', margin=margin, align_items='start')


def add_object_card(object_id, save_debug=False):
    post_data = {
        "operationName": "ObjectSelectById",
        "variables": {
            "objectId": object_id
        },
        "query": "fragment objectInfoFields on Object {\n  id\n  type\n  canceled\n  slug\n  url\n  wikiSlug\n  paywall\n  metadata {\n    state\n    descriptions {\n      long\n      short\n    }\n    names {\n      name\n      short\n      alt\n    }\n  }\n  features {\n    name\n    slug\n  }\n  franchises {\n    name\n    slug\n  }\n  genres {\n    name\n    slug\n  }\n  producers {\n    name\n    shortName\n    slug\n  }\n  publishers {\n    name\n    shortName\n    slug\n  }\n  primaryImage {\n    url\n  }\n  objectRegions {\n    id\n    name\n    objectId\n    region\n    ageRating {\n      id\n      name\n      slug\n      ageRatingTypeId\n      enabled\n      ageRatingType\n    }\n    releases {\n      id\n      date\n      estimatedDate\n      timeframeYear\n      platformAttributes {\n        id\n        name\n        slug\n      }\n    }\n    ageRatingDescriptors {\n      name\n    }\n    interactiveElements {\n      name\n    }\n  }\n}\n\nquery ObjectSelectById($objectId: ID!) {\n  objectSelectById(id: $objectId) {\n    ...objectInfoFields\n  }\n}\n"
    }
    api_data = get_api_data(post_data)
    if api_data:
        if save_debug:
            utils.write_file(api_data, './debug/object.json')
        object = api_data['data']['objectSelectById']
        card_content = '<div style="font-weight:bold; text-align:center;"><a href="https://www.ign.com' + object['url'] + '" target="_blank">' + object['metadata']['names']['name'] + '</a></div>'
        if object.get('producers'):
            card_content += '<div style="font-size:smaller;">Producer: '
            for it in object['producers']:
                card_content += '<a href="https://www.ign.com/games/producer/' + it['slug'] + '" target="_blank">' + it['name'] + '</a>, '
            card_content = card_content[:-2] + '</div>'
        if object.get('publishers'):
            card_content += '<div style="font-size:smaller;">Publisher: '
            for it in object['publishers']:
                card_content += '<a href="https://www.ign.com/games/publisher/' + it['slug'] + '" target="_blank">' + it['name'] + '</a>, '
            card_content = card_content[:-2] + '</div>'
        if object.get('objectRegions'):
            for it in object['objectRegions']:
                if it['region'] == 'US':
                    if it.get('releases'):
                        for release in it['releases']:
                            card_content += '<div style="font-size:smaller;">Platform: '
                            for platform in release['platformAttributes']:
                                card_content += '<a href="https://www.ign.com/games/platform/' + platform['slug'] + '" target="_blank">' + platform['name'] + '</a> (' + release['date'] + '), '
                            card_content = card_content[:-2] + '</div>'
                    if it.get('ageRating'):
                        card_content += '<div style="font-size:smaller;">Rating: ' + it['ageRating']['ageRatingType'] + ' ' + it['ageRating']['name'] + '</div>'
        card_image = ''
        footer_html = ''
        if object.get('wikiSlug'):
            post_data = {
                "operationName": "WikiNavigation",
                "variables": {
                    "slug": object['wikiSlug']
                },
                "query": "query WikiNavigation($slug: String!) {\n  wiki(slug: $slug) {\n    id\n    maps {\n      mapName\n      mapSlug\n    }\n    navigation {\n      label\n      url\n      subnav {\n        label\n        url\n        subnav {\n          label\n          url\n        }\n      }\n    }\n  }\n}\n"
            }
            wiki_nav = get_api_data(post_data)
            if wiki_nav:
                if save_debug:
                    utils.write_file(wiki_nav, './debug/wiki.json')
                card_image = '<div style="width:100%; height:100%; background:url(\'' + object['primaryImage']['url'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 0;"></div>'
                footer_html += '<details><summary><strong>Wiki Guide</strong></summary><ul>'
                for it in wiki_nav['data']['wiki']['navigation']:
                    footer_html += '<li><a href="https://www.ign.com/wikis/' + object['wikiSlug']
                    if it.get('url'):
                        footer_html += '/' + it['url'] + '" target="_blank">' + it['label']
                    else:
                        footer_html += '" target="_blank">Overview'
                    footer_html += '</a></li>'
                footer_html += '</ul></details>'
        if not card_image:
            card_image = '<div style="width:100%; height:100%; background:url(\'' + object['primaryImage']['url'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div>'

        return utils.format_small_card(card_image, card_content, footer_html, image_size='128px', content_style='padding:8px;', margin='1em auto', align_items='start')


def add_tier_list(tier_list_id, save_debug=False):
    tier_html = ''
    post_data = {
        "operationName": "TierListById",
        "variables": {
            "tierListId": tier_list_id
        },
        "query": "fragment tierListRequiredFields on TierList {\n  content {\n    id\n    slug\n    type\n    title\n    publishDate\n    url\n    state\n    updatedAt\n  }\n}\n\nfragment tierListFields on TierList {\n  ...tierListRequiredFields\n  tierListRows {\n    id\n    title\n  }\n  tierListItems {\n    id\n    caption\n    image {\n      id\n      url\n    }\n  }\n  communityRankings {\n    rankings {\n      tierListRowId\n      tierListItemIds\n    }\n  }\n  contributions\n}\n\nquery TierListById($tierListId: ID!) {\n  tierListById(id: $tierListId) {\n    ...tierListFields\n  }\n}\n"
    }
    api_data = get_api_data(post_data)
    if api_data:
        if save_debug:
            utils.write_file(api_data, './debug/tierlist.json')
        tier_list = api_data['data']['tierListById']
        tier_html += '<div style="font-size:larger; font-weight:bold; margin-top:1em;"><a href="https://www.ign.com' + tier_list['content']['url'] + '" target="_blank">' + tier_list['content']['title'] + '</a></div>'
        for ranking in tier_list['communityRankings']['rankings']:
            list_row = next((x for x in tier_list['tierListRows'] if x['id'] == ranking['tierListRowId']), None)
            tier_html += '<div style="display:grid; grid-template-areas:\'row-title row-content\'; grid-template-columns:4em auto; margin:8px 0;">'
            if list_row['title'] == 'S':
                color = '240,127,127'
            elif list_row['title'] == 'A':
                color = '242,188,125'
            elif list_row['title'] == 'B':
                color = '227,226,141'
            elif list_row['title'] == 'C':
                color = '199,226,141'
            elif list_row['title'] == 'D':
                color = '141,227,157'
            else:
                color = '127,127,127'
            tier_html += '<div style="grid-area:row-title; background-color:rgb(' + color + '); font-size:2em; font-weight:bold; text-align:center; padding:0.5em 0; border-radius:10px 0 0 10px;">' + list_row['title'] + '</div>'
            tier_html += '<div style="grid-area:row-content; background-color:rgba(' + color + ',0.25); padding:8px; border-radius:0 10px 10px 0;"><div style="display:flex; flex-wrap:wrap;">'
            for id in ranking['tierListItemIds']:
                list_item = next((x for x in tier_list['tierListItems'] if x['id'] == id), None)
                if list_item:
                    content_html = '<div style="font-size:small; font-weight:bold; text-transform:uppercase; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;">' + list_item['caption'] + '</div>'
                    if list_item.get('image'):
                        image_html = '<div style="width:100%; height:100%; background:url(\'' + list_item['image']['url'] + '\'); background-position:center; background-size:cover; text-align:center; border-radius:0 10px 10px 0;"></div>'
                    else:
                        image_html = '<div style="width:100%; height:100%; background-color:SlateGray; text-align:center; border-radius:0 10px 10px 0;"></div>'
                    tier_html += utils.format_small_card(image_html, content_html, image_size='50px', content_style='padding:4px;', margin='4px', align_items='center', image_position='right', width_style='width:250px;')
            tier_html += '</div></div></div>'
    return tier_html


def get_slideshow(slug, count=20, cursor=0, region='us'):
    post_data = {
        "operationName": "Slideshow",
        "variables": {
            "queryBy": "slug",
            "value": slug,
            "count": count,
            "cursor": cursor,
            "region": region
        },
        "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nquery Slideshow($queryBy: SlideshowQueryType!, $value: String!, $count: Int, $cursor: Cursor, $region: String) {\n  slideshow(queryBy: $queryBy, value: $value) {\n    content {\n      ...modernContentFeed\n      events\n      vertical\n      attributes {\n        type\n        attribute {\n          name\n        }\n      }\n      brand {\n        name\n      }\n      contentCategory {\n        name\n      }\n      contentImages {\n        images {\n          url\n        }\n      }\n    }\n    slideshowImages(count: $count, cursor: $cursor) {\n      pageInfo {\n        hasNext\n        nextCursor\n        total\n      }\n      images {\n        id\n        url\n        caption\n        embargoDate\n      }\n    }\n  }\n}\n"
    }
    return get_api_data(post_data)


def get_slideshow_content(url, args, site_json, save_debug):
    # print(url)
    if url.startswith('https:'):
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        if paths[0] != 'slideshows' or len(paths) < 2:
            logger.warning('unhandled slideshow url ' + url)
            return None
        slug = paths[1]
    else:
        slug = url

    slideshow_json = get_slideshow(slug)
    if not slideshow_json:
        return None
    if save_debug:
        utils.write_file(slideshow_json, './debug/slideshow.json')
    if slideshow_json.get('errors'):
        for error in slideshow_json['errors']:
            if error.get('message'):
                m = re.search(r'301: (/.*)', error['message'])
                if m:
                    logger.warning('url redirect to https://www.ign.com' + m.group(1))
                    return get_slideshow_content('https://www.ign.com' + m.group(1), args, site_json, save_debug)
        logger.warning('api errors getting data for ' + url)
        return None
    content_json = slideshow_json['data']['slideshow']['content']
    slideshow_images = slideshow_json['data']['slideshow']['slideshowImages']

    item = {}
    item['id'] = content_json['id']
    item['url'] = 'https://www.ign.com' + content_json['url']
    item['title'] = content_json['title']

    dt = get_datetime(content_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('updatedAt'):
        dt = get_datetime(content_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    if content_json.get('contributors'):
        item['authors'] = [{"name": x['name']} for x in content_json['contributors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": "IGN Slideshow"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['image'] = slideshow_images['images'][0]['url'] + '?width=1000'

    n = 0
    total = slideshow_images['pageInfo']['total']
    cursor = slideshow_images['pageInfo']['nextCursor']

    item['_gallery'] = []
    while n < total:
        if not slideshow_json:
            slideshow_json = get_slideshow(slug, 20, cursor)
            if not slideshow_json:
                break
            slideshow_images = slideshow_json['data']['slideshow']['slideshowImages']
            cursor = slideshow_images['pageInfo']['nextCursor']
            total = slideshow_images['pageInfo']['total']
        for image in slideshow_images['images']:
            img_src = image['url']
            thumb = image['url'] + '?width=640'
            if image.get('caption'):
                caption = image['caption']
            else:
                caption = ''
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
            n += 1
        slideshow_json = None

    gallery_url = config.server + '/gallery?url=' + quote_plus(item['url'])
    if 'embed' in args:
        caption = '<a href="' + item['url'] + '" target="_blank">View: ' + item['title'] + ' (' + str(total) + ' images)</a>'
        item['content_html'] = utils.add_gallery(item['_gallery'], gallery_url=gallery_url, gallery_caption=caption, show_gallery_poster=True)
    else:
        item['content_html'] = utils.add_gallery(item['_gallery'])
    return item


def get_video(slug):
    post_data = {
        "operationName": "Video",
        "variables": {
            "slug": slug
        },
        "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nquery Video($slug: String!, $region: String, $allowRedirect: Boolean) {\n  videoBySlug(slug: $slug, allowRedirect: $allowRedirect) {\n    content {\n      ...modernContentFeed\n      ads\n      ageGate\n      state\n      updatedAt\n      vertical\n      hrefLangs\n      comments\n      events\n      attributes {\n        type\n        attribute {\n          name\n        }\n      }\n      brand {\n        name\n      }\n      contentCategory {\n        id\n        name\n      }\n      seoTitle\n    }\n    videoMetadata {\n      adBreaks\n      captions\n      chatEnabled\n      descriptionHtml\n      disableRecirc\n      downloadable\n      duration\n      livestreamUrl\n      m3uUrl\n    }\n    assets {\n      url\n      width\n      height\n      fps\n    }\n    recommendations {\n      duration\n      title\n      url\n      videoId\n      extra {\n        videoSeries\n        active\n        liveOnAir\n      }\n      thumbnailUrl\n      slug\n    }\n    videoTasks {\n      start\n      end\n      checklistTask {\n        id\n        name\n        object {\n          id\n          paywall\n        }\n      }\n    }\n  }\n}\n"
    }
    return get_api_data(post_data)


def get_video_content(url, args, site_json, save_debug=False):
    # print(url)
    if url.startswith('https:'):
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        if paths[0] != 'videos' or len(paths) < 2:
            logger.warning('unhandled video url ' + url)
            return None
        slug = paths[1]
    else:
        slug = url

    api_data = get_video(slug)
    if not api_data:
        return None
    if save_debug:
        utils.write_file(api_data, './debug/video.json')
    if not api_data['data'].get('videoBySlug'):
        logger.warning('error getting video ' + url)
        if api_data['errors']:
            for error in api_data['errors']:
                logger.warning(error['message'])
        return None
    video_json = api_data['data']['videoBySlug']
    content_json = video_json['content']

    item = {}
    item['id'] = content_json['id']
    item['url'] = 'https://www.ign.com' + content_json['url']
    item['title'] = content_json['title']

    dt = get_datetime(content_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('updatedAt'):
        dt = get_datetime(content_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    if content_json.get('contributors'):
        item['authors'] = [{"name": x['name']} for x in content_json['contributors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": "IGN Videos"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['image'] = content_json['feedImage']['url'] + '?width=1000'

    caption = '<a href="{}">Watch: {}</a>'.format(item['url'], item['title'])

    item['content_html'] = ''
    if content_json.get('subtitle') and 'embed' not in args:
        item['content_html'] += '<p><em>' + content_json['subtitle'] + '</em></p>'

    if 'videoMetadata' in video_json and video_json['videoMetadata'].get('m3uUrl'):
        item['content_html'] += utils.add_video(video_json['videoMetadata']['m3uUrl'], 'application/x-mpegURL', item['image'], caption)
    elif 'assets' in video_json:
        videos = [it for it in video_json['assets'] if it['__typename'] == 'VideoAsset' and it.get('height')]
        if videos:
            video = utils.closest_dict(video_json['assets'], 'height', 540)
            item['content_html'] += utils.add_video(video['url'], 'video/mp4', item['image'], caption, use_videojs=True)

    if 'videoMetadata' in video_json and video_json['videoMetadata'].get('descriptionHtml'):
        item['summary'] = video_json['videoMetadata']['descriptionHtml']
        if 'embed' not in args:
            item['content_html'] += item['summary']
    return item


def get_article(slug, region='us'):
    post_data = {
        "operationName": "Article",
        "variables": {
            "slug": slug,
            "region": region
        },
        "query": "fragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nquery Article($slug: String!, $region: String) {\n  article(slug: $slug) {\n    ...modernArticleFeed\n    content {\n      state\n      updatedAt\n      modifications\n      comments\n      ads\n      headerImageUrl\n      excerpt\n      contributors: contributorsOrBylines {\n        ... on Contributor {\n          authorId\n          thumbnailUrl\n        }\n      }\n      vertical\n      hrefLangs\n      eventSlugs\n      events\n      attributes {\n        type\n        attribute {\n          name\n        }\n      }\n      primaryObject {\n        franchises {\n          name\n        }\n        genres {\n          slug\n        }\n        objectRegions(region: $region) {\n          releases {\n            id\n            date\n            estimatedDate\n            timeframeYear\n            platformAttributes {\n              id\n              name\n              slug\n            }\n          }\n        }\n      }\n      objects(count: 5, sortBy: \"object.name\", sortOrder: \"asc\", state: Published) {\n        ...objectBreadcrumbFields\n      }\n      seoTitle\n    }\n    article {\n      heroVideoContentId\n      heroVideoContentSlug\n      processedHtml\n      showCommerceDisclaimer\n    }\n    review {\n      id\n      score\n      scoreText\n      editorsChoice\n      scoreSummary\n      verdict\n      reviewedOn\n    }\n  }\n}\n"
    }
    return get_api_data(post_data)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] == 'videos':
        return get_video_content(paths[1], args, site_json, save_debug)
    elif paths[0] == 'slideshows':
        return get_slideshow_content(paths[1], args, site_json, save_debug)
    elif paths[0] != 'articles':
        logger.warning('unhandled url ' + url)
        return None

    api_data = get_article(paths[-1])
    if not api_data:
        return None
    article_json = api_data['data']['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    content_json = article_json['content']

    item = {}
    item['id'] = content_json['id']
    item['url'] = 'https://www.ign.com' + content_json['url']
    item['title'] = content_json['title']

    dt = get_datetime(content_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('updatedAt'):
        dt = get_datetime(content_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    if content_json.get('contributors'):
        item['authors'] = [{"name": x['name']} for x in content_json['contributors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": "IGN"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['content_html'] = ''
    if content_json.get('subtitle'):
        item['content_html'] += '<p><em>' + content_json['subtitle'] + '</em></p>'

    if article_json.get('article') and article_json['article'].get('heroVideoContentSlug'):
        video_item = get_video_content(article_json['article']['heroVideoContentSlug'], {"embed": True}, site_json, False)
        if video_item:
            item['image'] = video_item['image']
            item['content_html'] += video_item['content_html']
    elif content_json.get('headerImageUrl'):
        item['image'] = content_json['headerImageUrl'] + '?width=1000'
        item['content_html'] += utils.add_image(item['image'])
    elif content_json.get('feedImage') and content_json['feedImage'].get('url'):
        item['image'] = content_json['feedImage']['url'] + '?width=1000'
        item['content_html'] += utils.add_image(item['image'])

    if article_json.get('review'):
        item['summary'] = article_json['review']['verdict']
    elif content_json.get('excerpt'):
        item['summary'] = content_json['excerpt']

    # page_html = ''
    # for html in content_json['paginatedHtmlPage']:
    #     page_html += html
    #page_soup = BeautifulSoup(page_html, 'html.parser')

    if article_json.get('article'):
        page_soup = BeautifulSoup(article_json['article']['processedHtml'], 'html.parser')
        if save_debug:
            utils.write_file(str(page_soup), './debug/debug.html')

    for el in page_soup.find_all('aside'):
        if article_json.get('review') and el.select('h3 > u:-soup-contains("What we said about")'):
            el.name = 'div'
            el['style'] = 'margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb;'
        else:
            el.decompose()

    catalog_data = None
    for el in page_soup.find_all('section'):
        if el.get('data-transform'):
            if re.search(r'commerce-deal|mobile-ad-break|object-feedback|poll|faceoff|user-list', el['data-transform']):
                el.decompose()

            elif el['data-transform'] == 'image-with-caption':
                if el.get('data-caption'):
                    caption = unquote_plus(el['data-caption'])
                elif el.get('data-image-title'):
                    caption = unquote_plus(el['data-image-title'])
                else:
                    caption = ''
                el_html = utils.add_image(el['data-image-url'], caption, link=el.get('data-image-link'))
                el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'slideshow':
                slideshow_item = get_slideshow_content(el['data-slug'], {"embed": True}, site_json, save_debug)
                if slideshow_item:
                    el.replace_with(BeautifulSoup(slideshow_item['content_html'], 'html.parser'))
                else:
                    logger.warning('unable to get slideshow data for ' + el['data-slug'])

            elif el['data-transform'] == 'ignvideo':
                video_item = get_video_content(el['data-slug'], {"embed": True}, site_json, False)
                if video_item:
                    el.replace_with(BeautifulSoup(video_item['content_html'], 'html.parser'))
                else:
                    logger.warning('unable to get video data for ' + el['data-slug'])

            elif el['data-transform'] == 'quoteBox':
                el_html = utils.add_pullquote(el.get_text())
                el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'divider':
                el_html = '<hr style="width:80%; margin:1em auto;"/>'
                el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'catalog-item-wrapper':
                el.unwrap()

            elif el['data-transform'] == 'catalog-carousel':
                if not catalog_data or catalog_data['data']['catalogById']['content']['id'] != el['data-catalogid']:
                    catalog_data = get_catalog_by_id(el['data-catalogid'])
                    if catalog_data:
                        if save_debug:
                            utils.write_file(catalog_data, './debug/catalog.json')
                if catalog_data:
                    el_html = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                    for it in json.loads(el['data-items']):
                        catalog_item = next((x for x in catalog_data['data']['catalogById']['items'] if x['id'] == it), None)
                        if catalog_item:
                            el_html += '<div style="flex:1; min-width:360px;">' + add_catalog_item(catalog_item, margin='auto') + '</div>'
                    el_html += '</div>'
                    el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'catalog-item':
                if not catalog_data or catalog_data['data']['catalogById']['content']['id'] != el['data-catalogid']:
                    catalog_data = get_catalog_by_id(el['data-catalogid'])
                    if catalog_data:
                        if save_debug:
                            utils.write_file(catalog_data, './debug/catalog.json')
                if catalog_data:
                    catalog_item = next((it for it in catalog_data['data']['catalogById']['items'] if it['id'] == int(el['data-id'])), None)
                    if catalog_item:
                        el.replace_with(BeautifulSoup(add_catalog_item(catalog_item), 'html.parser'))

            elif el['data-transform'] == 'prosAndCons':
                data_json = json.loads(unquote_plus(el['data-json']))
                el_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;"><div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                for it in data_json['pros']:
                    el_html += '<li>' + it + '</li>'
                el_html += '</ul></div><div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">CONS</div><ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>'
                for it in data_json['cons']:
                    el_html += '<li>' + it + '</li>'
                el_html += '</ul></div></div>'
                el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'object-card':
                el_html = add_object_card(el['data-id'])
                if el_html:
                    el.replace_with(BeautifulSoup(el_html, 'html.parser'))

            elif el['data-transform'] == 'tier-list':
                el_html = add_tier_list(el['data-id'], True)
                if el_html:
                    el.replace_with(BeautifulSoup(el_html, 'html.parser'))
            else:
                logger.warning('unhandled section data-transform=' + el['data-transform'] + ' in ' + url)
        elif el.get('class') and 'article-page' in el['class']:
            el.unwrap()

    for el in page_soup.find_all('a', recursive=False):
        if el.find('img', class_='article-image-full-size'):
            el_html = utils.add_image(el['href'] + '?width=1000', link=el['href'])
            el.replace_with(BeautifulSoup(el_html, 'html.parser'))

    for el in page_soup.select('div[style*="text-align: center"]:has( > a > img)'):
        if re.search(r'\.(gif|jpg|jpeg|png)$', el.a['href'], flags=re.I):
            el_html = utils.add_image(el.a['href'] + '?width=1000')
            el.replace_with(BeautifulSoup(el_html, 'html.parser'))

    for el in page_soup.find_all('blockquote', class_='twitter-tweet'):
        tweet_url = el.find_all('a')[-1]['href']
        if re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url):
            el_html = utils.add_embed(tweet_url)
            el.replace_with(BeautifulSoup(el_html, 'html.parser'))

    # lead = False
    # if content_json.get('headerImageUrl'):
    #     item['content_html'] += utils.add_image(content_json['headerImageUrl'] + '?width=1000')
    #     lead = True
    # elif content_json.get('canWatchRead') and content_json['canWatchRead'] == True and content_json.get('relatedMediaId'):
    #     # Use the associated video as the lead (usually for reviews)
    #     video_json = get_video_data('', content_json['relatedMediaId'])
    #     if video_json:
    #         poster = video_json['thumbnailUrl'] + '?width=1000'
    #         caption = video_json['title']
    #         video = utils.closest_dict(video_json['assets'], 'width', 640)
    #         item['content_html'] += utils.add_video(video['url'], 'video/mp4', poster, caption)
    #         lead = True
    # if not lead and item.get('image'):
    #     item['content_html'] += utils.add_image(item['image'])

    verdict = ''
    if article_json.get('review'):
        item['content_html'] += '<div style="margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#aaa;">'
        if article_json['review']['editorsChoice'] == True:
            item['content_html'] += '<div style="text-align:center;"><span style="color:white; background-color:red; padding:4px; font-weight:bold;">EDITOR\'S CHOICE</span></div>'
        if article_json['review'].get('score'):
            item['content_html'] += utils.add_score_gauge(article_json['review']['score'] * 10, str(article_json['review']['score']), margin='8px auto')
        if article_json['review'].get('scoreText'):
            item['content_html'] += '<div style="text-align:center; font-weight:bold;">' + article_json['review']['scoreText'].upper() + '</div>'
        if article_json['review'].get('scoreSummary'):
            item['content_html'] += '<p><em>' + article_json['review']['scoreSummary'] + '</em></p>'
        item['content_html'] += '<ul style="font-size:0.8em;">'
        if content_json.get('objects'):
            for object in content_json['objects']:
                if object.get('objectRegions'):
                    for object_region in object['objectRegions']:
                        if object_region.get('ageRating'):
                            desc = []
                            if object_region.get('ageRatingDescriptors'):
                                for it in object_region['ageRatingDescriptors']:
                                    desc.append(it['name'])
                            if desc:
                                item['content_html'] += '<li>Rating: {} ({})</li>'.format(object['ageRating']['name'], ', '.join(desc))
                                #item['tags'] += desc
                            else:
                                item['content_html'] += '<li>Rating: {}</li>'.format(object['ageRating']['name'])

                        if object_region.get('releases'):
                            releases = {}
                            for release in object_region['releases']:
                                if release.get('timeframeYear'):
                                    date = release['timeframeYear']
                                elif release.get('date'):
                                    dt = get_datetime(release['date'])
                                    date = utils.format_display_date(dt, date_only=True)
                                else:
                                    date = 'N/A'
                                if not releases.get(date):
                                    releases[date] = []
                                if release.get('platformAttributes'):
                                    for it in release['platformAttributes']:
                                        if it['name'] not in releases[date]:
                                            releases[date].append(it['name'])
                            for key, val in releases.items():
                                item['content_html'] += '<li>Released ' + key
                                if val:
                                    item['content_html'] += ' for ' + ', '.join(val)
                                item['content_html'] += '</li>'

                for key, val in object.items():
                    if isinstance(val, list) and key != 'objectRegions':
                        attrs = []
                        for it in val:
                            if it.get('name'):
                                attrs.append(it['name'])
                                #item['tags'].append(it['name'])
                        if attrs:
                            item['content_html'] += '<li>' + key.capitalize() + ': ' + ', '.join(attrs) + '</li>'
        item['content_html'] += '</ul></div>'
        verdict = '<h2>Verdict</h2><p>{}</p>'.format(article_json['review']['verdict'])

    if verdict:
        page_soup.append(BeautifulSoup(verdict, 'html.parser'))

    item['content_html'] += str(page_soup)

    if content_json.get('primaryObject'):
        r = curl_cffi.get('https://pg.ignimgs.com/pgvideo.js?b=IGN&s=' + content_json['primaryObject']['slug'], impersonate="chrome", proxies=config.proxies)
        if r.status_code == 200:
            i = r.text.find('(') + 1
            j = r.text.rfind(')')
            playlist = json.loads(r.text[i:j])
            if save_debug:
                utils.write_file(playlist, './debug/playlist.json')
            if len(playlist) > 0:
                for it in playlist:
                    if it.get('slug') and (content_json['primaryObject']['slug'] in it['slug'] or content_json['primaryObject']['metadata']['names']['name'].lower() in it['title'].lower()):
                        video_item = get_video_content(it['slug'], {"embed": True}, site_json, False)
                        if video_item:
                            item['content_html'] += video_item['content_html']
                            break

    if not item.get('tags'):
        del item['tags']
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if split_url.query:
        params = parse_qs(split_url.query)
    else:
        params = None
    content_feed = []
    feed_title = ''
    if 'rss' in paths:
        # https://www.ign.com/rss/v2/articles/feed
        # https://www.ign.com/rss/v2/articles/feed?categories=column
        # https://www.ign.com/rss/v2/articles/feed?categories=news
        # https://www.ign.com/rss/v2/articles/feed?categories=reviews
        # https://www.ign.com/rss/v2/articles/feed?channel=movies
        # https://www.ign.com/rss/v2/articles/feed?channel=nintendo
        # https://www.ign.com/rss/v2/articles/feed?tags=trailer
        # https://www.ign.com/rss/v2/articles/feed?vertical=games
        # https://www.ign.com/rss/v2/articles/feed?vertical=tech
        # https://www.ign.com/rss/v2/videos/feed
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    elif len(paths) == 0 or paths[0] == 'news':
        post_data = {
            "operationName": "HomepageContentFeed",
            "variables": {
                "filter": "Latest",
                "region": "us",
                "startIndex": 0,
                "count": 12,
                "newsOnly": False
            },
            "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment modernVideoFeed on ModernVideo {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n  }\n  videoMetadata {\n    duration\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nquery HomepageContentFeed($filter: HomepageFeedFilterEnum!, $region: String, $count: Int, $startIndex: Int, $newsOnly: Boolean) {\n  homepage {\n    contentFeed(filter: $filter, region: $region, count: $count, startIndex: $startIndex, newsOnly: $newsOnly) {\n      pagination {\n        total\n        isMore\n        endIndex\n      }\n      feedItems {\n        ...feedItem\n      }\n    }\n  }\n}\n"
        }
        if params and params.get('filter'):
            post_data['variables']['filter'] = params['filter'][0].title()
        elif len(paths) > 1:
            post_data['variables']['filter'] = paths[1].title()
        if post_data['variables']['filter'].lower() == 'playstation':
            post_data['variables']['filter'] = 'PlayStation'
        api_data = get_api_data(post_data)
        if api_data:
            content_feed = api_data['data']['homepage']['contentFeed']

    elif paths[0] == 'reviews' or paths[0] == 'editors-choice':
        post_data = {
            "operationName": "ReviewsContentFeed",
            "variables": {
                "filter": "All",
                "region": "us",
                "startIndex": 0,
                "count": 10,
                "editorsChoice": False,
                "sortOption": "Latest"
            },
            "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment modernArticleReviewFeed on ModernArticle {\n  ...modernArticleFeed\n  review {\n    score\n  }\n}\n\nquery ReviewsContentFeed(\n  $filter: ReviewFilterEnum!\n  $sortOption: ReviewSortOptionEnum\n  $scoreRange: String\n  $gamePlatformSlugs: [String]\n  $genreSlugs: [String]\n  $editorsChoice: Boolean\n  $region: String\n  $count: Int\n  $startIndex: Int\n) {\n  reviewContentFeed(\n    filter: $filter\n    sortOption: $sortOption\n    scoreRange: $scoreRange\n    gamePlatformSlugs: $gamePlatformSlugs\n    genreSlugs: $genreSlugs\n    editorsChoice: $editorsChoice\n    region: $region\n    count: $count\n    startIndex: $startIndex\n  ) {\n    pagination {\n      total\n      isMore\n      endIndex\n    }\n    feedItems {\n      ...modernArticleReviewFeed\n    }\n  }\n}\n"
        }
        if params and params.get('filter'):
            post_data['variables']['filter'] = params['filter'][0].title()
        elif len(paths) > 1:
            post_data['variables']['filter'] = paths[1].replace('-', ' ').title().replace(' ', '')
        if post_data['variables']['filter'] == 'Tv':
            post_data['variables']['filter'] = 'TV'

        platform = ''
        if len(paths) > 2 and paths[1] == 'games':
            platform = paths[2].lower()
            post_data['variables']['gamePlatformSlugs'] = []
            post_data['variables']['gamePlatformSlugs'].append(platform)
            platforms = {
                "xbox-4": "Xbox Series X|S",
                "gcn": "Nintendo GameCube",
                "3ds": "Nintendo 3DS",
                "new-nintendo-3ds": "Nintendo New 3DS",
                "gb": "Nintendo Game Boy",
                "gba": "Nintendo Game Boy Advance",
                "n64": "Nintendo 64",
                "nds": "Nintendo DS",
                "wii": "Nintendo Wii",
                "wii-u": "Nintendo Wii U",
                "ipad": "iPad",
                "iPhone": "iPhone",
                "nng": "N-Gage",
                "vita": "PlayStation Vita",
                "pc": "PC",
                "ps": "PlayStation",
                "ps2": "PlayStation 2",
                "ps3": "PlayStation 3",
                "ps4": "PlayStation 4",
                "ps5": "PlayStation 5",
                "psp": "PlayStation Portable (PSP)"
            }
            if platform in platforms:
                platform = platforms[platform] + ' '
            else:
                platform = platform.replace('-', ' ').title() + ' '

        if paths[0] == 'editors-choice':
            post_data['variables']['editorsChoice'] = True
            if post_data['variables']['filter'] == 'All':
                feed_title = 'Best ' + platform + 'Reviews'
            else:
                feed_title = 'Best ' + platform + post_data['variables']['filter']
        else:
            if post_data['variables']['filter'] == 'All':
                feed_title = 'All Reviews'
            else:
                feed_title = platform + post_data['variables']['filter'] + ' Reviews'

        if params and params.get('genre'):
            post_data['variables']['genreSlugs'] = []
            post_data['variables']['genreSlugs'].append(params['genre'][0])
            feed_title += ' [' + params['genre'][0].replace('-', ' ').title() + ']'

        feed_title += ' - IGN'

        api_data = get_api_data(post_data)
        if api_data:
            content_feed = api_data['data']['reviewContentFeed']

    elif paths[0] == 'columns':
        if len(paths) == 1:
            post_data = {
                "operationName": "ColumnAllSeries",
                "variables": {},
                "query": "fragment columnSeriesFields on ColumnSeries {\n  id\n  slug\n  name\n  description\n  columnCoverImage\n  logoLight\n  logoDark\n}\n\nquery ColumnAllSeries {\n  allColumnSeries {\n    ...columnSeriesFields\n  }\n}\n",
            }
            all_series = get_api_data(post_data)
            if all_series:
                if save_debug:
                    utils.write_file(all_series, './debug/series.json')
                post_data = {
                    "operationName": "ColumnSeries",
                    "variables": {
                        "count": 3,
                        "slug": "",
                        "startIndex": 0,
                        "region": "us"
                    },
                    "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment columnSeriesFields on ColumnSeries {\n  id\n  slug\n  name\n  description\n  columnCoverImage\n  logoLight\n  logoDark\n}\n\nquery ColumnSeries($slug: String, $id: ID, $cursor: Cursor, $startIndex: Int, $count: Int, $region: String) {\n  columnSeries(startIndex: $startIndex, cursor: $cursor, count: $count, slug: $slug, id: $id) {\n    pagination {\n      total\n      isMore\n      endIndex\n      startIndex\n      nextCursor\n      count\n    }\n    series {\n      ...columnSeriesFields\n    }\n    articles {\n      ...modernArticleFeed\n    }\n  }\n}\n",
                }
                content_feed = {
                    "feedItems": []
                }
                for series in all_series['data']['allColumnSeries']:
                    post_data['variables']['slug'] = series['slug']
                    api_data = get_api_data(post_data)
                    if api_data:
                        content_feed['feedItems'] += api_data['data']['columnSeries']['articles']
        else:
            post_data = {
                "operationName": "ColumnSeries",
                "variables": {
                    "count": 10,
                    "slug": paths[1],
                    "startIndex": 0,
                    "region": "us"
                },
                "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment columnSeriesFields on ColumnSeries {\n  id\n  slug\n  name\n  description\n  columnCoverImage\n  logoLight\n  logoDark\n}\n\nquery ColumnSeries($slug: String, $id: ID, $cursor: Cursor, $startIndex: Int, $count: Int, $region: String) {\n  columnSeries(startIndex: $startIndex, cursor: $cursor, count: $count, slug: $slug, id: $id) {\n    pagination {\n      total\n      isMore\n      endIndex\n      startIndex\n      nextCursor\n      count\n    }\n    series {\n      ...columnSeriesFields\n    }\n    articles {\n      ...modernArticleFeed\n    }\n  }\n}\n",
            }
            api_data = get_api_data(post_data)
            if api_data:
                content_feed = api_data['data']['columnSeries']
                content_feed['feedItems'] = content_feed.pop('articles')
                feed_title = api_data['data']['columnSeries']['series']['name']

    elif len(paths) == 1:
        post_data = {
            "operationName": "ChannelInfo",
            "variables": {
                "slug": paths[0]
            },
            "query": "fragment channelInfoFields on Channel {\n  id\n  slug\n  displayName\n  color\n  title\n  description\n  filters\n  adOps {\n    tags\n    categories\n    genre\n    platforms\n  }\n}\n\nquery ChannelInfo($slug: String!) {\n  channel(slug: $slug) {\n    ...channelInfoFields\n  }\n}\n",
        }
        api_data = get_api_data(post_data)
        if api_data:
            feed_title = api_data['data']['channel']['title']
            channel_name = api_data['data']['channel']['displayName']
        post_data = {
            "operationName": "ChannelContentFeed",
            "variables": {
                "slug": paths[0],
                "region": "us",
                "filter": "All",
                "startIndex": 0,
                "count": 10
            },
            "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment modernVideoFeed on ModernVideo {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n  }\n  videoMetadata {\n    duration\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nquery ChannelContentFeed($slug: String!, $region: String, $filter: ChannelFeedFilterEnum!, $count: Int, $startIndex: Int) {\n  channel(slug: $slug) {\n    id\n    channelFeed(filter: $filter, region: $region, count: $count, startIndex: $startIndex) {\n      pagination {\n        total\n        isMore\n        endIndex\n      }\n      feedItems {\n        ...feedItem\n      }\n    }\n  }\n}\n"
        }
        if params and params.get('filter'):
            post_data['variables']['filter'] = params['filter'][0].title()

        if paths[0] == 'videos':
            if post_data['variables']['filter'] == 'All':
                post_data['variables']['filter'] = 'Videos'
                feed_title = 'Latest Videos'
            else:
                feed_title = post_data['variables']['filter'] + ' Videos'
        elif post_data['variables']['filter'] == 'All':
            feed_title = 'All ' + channel_name + ' News'
        elif post_data['variables']['filter'] == 'Popular':
            feed_title = 'Popular ' + channel_name + ' News'
        elif post_data['variables']['filter'] == 'Videos':
            feed_title = channel_name + ' Videos'
        elif post_data['variables']['filter'] == 'Articles':
            feed_title = channel_name + ' Articles'
        elif post_data['variables']['filter'] == 'Reviews':
            feed_title = channel_name + ' Reviews'

        api_data = get_api_data(post_data)
        if api_data:
            content_feed = api_data['data']['channel']['channelFeed']

    elif paths[0] == 'events':
        post_data = {
            "operationName": "FeedPageInfo",
            "variables": {
                "slug": paths[1]
            },
            "query": "query FeedPageInfo($slug: String!) {\n  feedPage(slug: $slug) {\n    id\n    slotterSlugs\n    description\n    displayName\n    filters\n    allowAdTheme\n    nonIndexable\n    allFeed\n  }\n}\n",
        }
        api_data = get_api_data(post_data)
        if api_data:
            feed_title = api_data['data']['feedPage']['displayName']
        post_data = {
            "operationName": "FeedPageContentFeed",
            "variables": {
                "slug": paths[1],
                "filter": "Latest",
                "region": "us",
                "startIndex": 0,
                "count": 10,
                "allFeed": False
            },
            "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment modernVideoFeed on ModernVideo {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n  }\n  videoMetadata {\n    duration\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nquery FeedPageContentFeed($slug: String!, $region: String, $filter: String!, $count: Int, $startIndex: Int, $allFeed: Boolean) {\n  feedPage(slug: $slug) {\n    id\n    contentFeed(region: $region, filter: $filter, count: $count, startIndex: $startIndex, allFeed: $allFeed) {\n      pagination {\n        total\n        isMore\n        endIndex\n      }\n      feedItems {\n        ...feedItem\n      }\n    }\n  }\n}\n"
        }
        if params and params.get('filter'):
            post_data['variables']['filter'] = params['filter'][0].title()
            if feed_title:
                feed_title += ' [' + post_data['variables']['filter'] + ']'
        api_data = get_api_data(post_data)
        if api_data:
            content_feed = api_data['data']['feedPage']['contentFeed']

    elif paths[0] == 'person':
        post_data = {
            "operationName": "AuthorInfo",
            "variables": {
                "nickname": paths[1]
            },
            "query": "query AuthorInfo($nickname: String) {\n  author: contributor(nickname: $nickname) {\n    id\n    authorId\n    name\n    profileUrl\n    thumbnailUrl\n    nickname\n    position\n    location\n    aboutMe\n    bio\n    twitterHandle\n    backgroundImageUrl\n  }\n}\n"
        }
        api_data = get_api_data(post_data)
        if api_data:
            feed_title = api_data['data']['author']['name'] + ' - IGN'
            post_data = {
                "operationName": "AuthorContentFeed",
                "variables": {
                    "authorId": api_data['data']['author']['authorId'],
                    "filter": "Latest",
                    "count": 10
                },
                "query": "fragment modernContentFeedRequiredFields on ModernContent {\n  id\n  type\n  title\n  subtitle\n  promoteAt\n  publishDate\n  slug\n  feedTitle\n  feedImage {\n    url\n  }\n  v3Id\n  url\n}\n\nfragment contributorsOrBylines on ContributorOrByline {\n  ... on Contributor {\n    id\n    name\n    nickname\n  }\n  ... on Byline {\n    name\n  }\n}\n\nfragment objectBreadcrumbFields on Object {\n  id\n  url\n  slug\n  type\n  metadata {\n    names {\n      name\n      alt\n      short\n    }\n  }\n  objectRegions(region: $region) {\n    id\n    name\n    region\n    releases {\n      id\n      date\n      platformAttributes {\n        id\n        name\n      }\n    }\n  }\n  franchises {\n    name\n    slug\n  }\n}\n\nfragment modernContentFeed on ModernContent {\n  ...modernContentFeedRequiredFields\n  contributors: contributorsOrBylines {\n    ...contributorsOrBylines\n  }\n  primaryObject {\n    ...objectBreadcrumbFields\n  }\n}\n\nfragment abTest on ABTest {\n  id\n  represents\n  values\n  winnerIndex\n}\n\nfragment sponsorshipFields on Sponsorship {\n  id\n  type\n  name\n  clickthroughUrl\n  brandAssetImage {\n    id\n    url\n  }\n}\n\nfragment modernArticleFeed on ModernArticle {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n    sponsorships {\n      ...sponsorshipFields\n    }\n    contentCategory {\n      id\n      name\n    }\n    brand {\n      id\n      slug\n      name\n      logoLight\n      logoDark\n    }\n    sequenceNumber\n  }\n}\n\nfragment modernVideoFeed on ModernVideo {\n  content {\n    ...modernContentFeed\n    abTests {\n      ...abTest\n    }\n  }\n  videoMetadata {\n    duration\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nfragment feedItem on FeedItem {\n  ...modernArticleFeed\n  ...modernVideoFeed\n  ... on Faceoff {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n  ... on Promotion {\n    content {\n      ...modernContentFeed\n      abTests {\n        ...abTest\n      }\n    }\n  }\n}\n\nquery AuthorContentFeed($authorId: Int, $filter: String!, $count: Int, $startIndex: Int, $region: String) {\n  contributor(authorId: $authorId) {\n    id\n    contentFeed(filter: $filter, count: $count, startIndex: $startIndex) {\n      pagination {\n        isMore\n        endIndex\n      }\n      feedItems {\n        ...feedItem\n        ... on ContentItem {\n          id\n          title\n          slug\n          url\n        }\n      }\n    }\n  }\n}\n"
            }
            if params and params.get('filter'):
                post_data['variables']['filter'] = params['filter'][0].title()
            elif len(paths) > 2:
                post_data['variables']['filter'] = paths[2].replace('-', ' ').title().replace(' ', '')
            api_data = get_api_data(post_data)
            if api_data:
                content_feed = api_data['data']['contributor']['contentFeed']

    if not content_feed:
        return None
    if save_debug:
        utils.write_file(content_feed, './debug/feed.json')

    n = 0
    feed_items = []
    for it in content_feed['feedItems']:
        content_url = 'https://www.ign.com' + it['content']['url']
        if save_debug:
            logger.debug('getting content from ' + content_url)
        item = get_content(content_url, args, site_json, save_debug)
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
