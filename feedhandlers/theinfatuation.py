import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import dirt

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1000):
    # https://cloudinary.com/documentation/image_transformations
    m = re.search(r'https?://res.cloudinary.com/.*?/upload/', image['original_secure_url'])
    if m:
        return m.group(0) + 'w_' + str(width) + '/f_auto/q_auto/' + image['public_id']
    return image['original_secure_url']


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1] + '.json'
        else:
            path = split_url.path + '.json'
        query = '?city=' + paths[0]
        if len(paths) == 2:
            query += 'sectionName=' + paths[1]
        elif len(paths) == 3:
            if paths[1] == 'cuisines' or paths[1] == 'neighborhoods' or paths[1] == 'perfect-for':
                query += 'sectionName=' + paths[1] + '&subsectionName=' + paths[2]
            else:
                query += '&slug=' + paths[2]
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url, site_json=site_json)
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


def add_review_info(review, apollo_state):
    review_html = ''
    rating = 'N/A' if not review['rating'] else review['rating']
    review_url = 'https://www.theinfatuation.com' + review['canonicalPath'] + '/reviews/' + apollo_state[review['slug']['__ref']]['name']
    review_html += '<div style="display:grid; grid-gap:1em; grid-template-columns:auto auto; margin-bottom:1em;"><div style="font-size:3em; font-weight:bold; margin:auto 0 auto 0;"><a href="{}" style="text-decoration:none;" target="_blank">{}</a></div><div style="margin:auto 0 auto 0; font-style:italic;">{}</div></div>'.format(review_url, rating, review['preview'])
    location = ', '.join(list(filter(None, [review['venue']['street'], review['venue']['city'], review['venue']['state'], review['venue']['postalCode'], review['venue']['country']])))
    review_html += '<div>Location: <a href="https://www.google.com/maps/search/?api=1&query={}%2C+{}" target="_blank">{}</a></div>'.format(quote_plus(review['venue']['name']), quote_plus(location), location)
    if review['venue'].get('price'):
        review_html += '<div>Price: ' + '$'*review['venue']['price'] + '</div>'
    for key, val in review.items():
        if key.startswith('cuisineTagsCollection'):
            if val.get('items'):
                review_html += '<div>Cuisine: ' + ', '.join([apollo_state[x['__ref']]['name'] for x in val['items']])
        elif key.startswith('perfectForCollection'):
            if val.get('items'):
                review_html += '<div>Perfect for: ' + ', '.join([x['name'] for x in val['items']])
    return review_html


def add_caption(caption, apollo_state):
    caption_html = ''
    gallery_images = []
    if caption.get('gallery') and caption['gallery'].get('assets'):
        n = len(caption['gallery']['assets'])
        if n > 1:
            caption_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for i, image in enumerate(caption['gallery']['assets']):
                img_src = resize_image(image, 1200)
                thumb = resize_image(image, 800)
                if image.get('metadata') and image['metadata'].get('photo_creds'):
                    img_caption = image['metadata']['photo_creds']
                else:
                    img_caption = ''
                if i == 0 and n > 2:
                    caption_html += utils.add_image(thumb, img_caption, link=img_src)
                else:
                    caption_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, img_caption, link=img_src) + '</div>'
                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
            if n > 2 and i % 2 != 0:
                caption_html += '<div style="flex:1; min-width:360px;"></div>'
            caption_html += '</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            caption_html += '<div><small><a href="{}" target="_blank">View photo gallery</a>'.format(gallery_url)
            if caption['gallery'].get('name'):
                caption_html += ': ' + caption['gallery']['name']
            caption_html += '</small></div>'
        else:
            image = caption['gallery']['assets'][0]
            img_src = resize_image(image, 1200)
            thumb = resize_image(image)
            img_captions = []
            if caption['gallery'].get('name'):
                img_captions.append(caption['gallery']['name'])
            if image.get('metadata') and image['metadata'].get('photo_creds'):
                img_captions.append(image['metadata']['photo_creds'])
            img_caption = ' | '.join(img_captions)
            gallery_images.append({"src": img_src, "caption": img_caption, "thumb": thumb})
            caption_html += utils.add_image(thumb, img_caption, link=img_src)

    if caption.get('review') and caption['review'].get('__ref'):
        review = apollo_state[caption['review']['__ref']]
        if not gallery_images and review.get('headerImageV2'):
            img_src = resize_image(review['headerImageV2'][0])
            if review['headerImageV2'][0].get('metadata') and review['headerImageV2'][0]['metadata'].get('photo_creds'):
                img_caption = review['headerImageV2'][0]['metadata']['photo_creds']
            else:
                img_caption = ''
            caption_html += utils.add_image(img_src, img_caption)
        caption_html += '<h2>' + review['title'] + '</h2>'
        caption_html += add_review_info(review, apollo_state)

    if caption.get('content') and caption['content'].get('json'):
        caption_html += dirt.render_content(caption['content']['json'], None)

    caption_html += '<div>&nbsp;</div>'
    return caption_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    apollo_state = next_data['pageProps']['initialApolloState']
    post_json = None
    for key, val in apollo_state['ROOT_QUERY'].items():
        if key.lower().startswith('post'):
            if val.get('items'):
                if val['items'][0].get('__ref'):
                    post_json = apollo_state[val['items'][0]['__ref']]
                else:
                    post_json = val['items'][0]
            break
    if not post_json:
        logger.warning('unable to determine post data in ' + url)
        return None

    item = {}
    item['id'] = apollo_state[post_json['sys']['__ref']]['id']
    item['url'] = url
    if post_json.get('seoTitle'):
        item['title'] = post_json['seoTitle']
    elif post_json.get('title'):
        item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['authors'] = []
    item['tags'] = []
    content_v2_body = None
    for key, val in post_json.items():
        if key.startswith('contributorCollection'):
            for it in val['items']:
                item['authors'].append({"name": apollo_state[it['__ref']]['name']})
        elif key.startswith('neighborhoodTagsCollection') or key.startswith('cuisineTagsCollection') or key.startswith('perfectForCollection'):
            for it in val['items']:
                if it.get('__ref'):
                    item['tags'].append(apollo_state[it['__ref']]['name'])
                elif it.get('name'):
                    item['tags'].append(it['name'])
        elif key.startswith('contentV2BodyCollection'):
            content_v2_body = val

    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        del item['authors']

    if post_json.get('city') and post_json['city']['name'] not in item['tags']:
        item['tags'].append(post_json['city']['name'])
    if post_json.get('venue') and post_json['venue']['name'] not in item['tags']:
        item['tags'].append(post_json['venue']['name'])
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if post_json.get('seoMetaDescription'):
        item['summary'] = post_json['seoMetaDescription']
    elif post_json['preview']:
        item['summary'] = post_json['preview']
    if 'summary' in item and post_json['__typename'] != 'PostReview':
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if post_json.get('headerImageV2'):
        item['image'] = resize_image(post_json['headerImageV2'][0])
        # TODO: caption
        if post_json['headerImageV2'][0]['metadata'].get('photo_creds'):
            caption = post_json['headerImageV2'][0]['metadata']['photo_creds']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['image'], caption)

    if post_json['__typename'] == 'PostReview':
        item['content_html'] += add_review_info(post_json, apollo_state)

    if post_json.get('contentV2Intro'):
        item['content_html'] += dirt.render_content(post_json['contentV2Intro']['json'], None)

    if post_json.get('content'):
        item['content_html'] += dirt.render_content(post_json['content']['json'], post_json['content'].get('links'))

    if content_v2_body and content_v2_body.get('items'):
        if post_json.get('contentV2BodyHeader'):
            item['content_html'] += '<h2>' + post_json['contentV2BodyHeader'] + '</h2>'
        for content in content_v2_body['items']:
            if content['__typename'] == 'CaptionGroup':
                for key, val in apollo_state['ROOT_QUERY'].items():
                    if key.startswith('captionGroup') and val['sys']['__ref'] == content['sys']['__ref']:
                        if val.get('heading'):
                            item['content_html'] += '<h2>' + val['heading'] + '</h2>'
                        for k, v in val.items():
                            if k.startswith('spotsCollection'):
                                for it in v['items']:
                                    item['content_html'] += add_caption(it, apollo_state)
            elif content['__typename'] == 'Caption':
                item['content_html'] += add_caption(content, apollo_state)
            else:
                logger.warning('unhandled contentV2BodyCollection item type ' + content['__typename'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    split_url = urlsplit(url)

    for key, val in next_data['pageProps']['initialApolloState']['ROOT_QUERY'].items():
        if key.startswith('sectionCollection') and split_url.path in key:
            section_id = val['items'][0]['sys']['__ref'].split(':')[1]
            feed_title = val['items'][0]['name']
            break

    gql_query = 'query getPosts($query: String $geoPoint: GeoPointInput $geoBounds: GeoBoundsInput $cuisineIds: [String!] $categoryIds: [String!] $first: Int $ratings: [Float!] $prices: [Price] $after: Base64String $reservations: Reservation $postType: [PostType] $canonicalPath: String $sectionIds: [String!] $searchType: SearchType $contributorSlug: String $neighborhoodSectionIds: [String!] $cuisineSectionIds: [String!] $categorySectionIds: [String!] $gate: [Gate] = [UNSPECIFIED] $saved: Boolean $launchDarklyContext: LaunchDarklyContextInput) { postSearch( input: {postType: $postType geoPoint: $geoPoint geoBounds: $geoBounds term: $query cuisineIds: $cuisineIds categoryIds: $categoryIds first: $first ratings: $ratings prices: $prices after: $after reservations: $reservations canonicalPath: $canonicalPath sectionIds: $sectionIds searchType: $searchType contributorSlug: $contributorSlug neighborhoodSectionIds: $neighborhoodSectionIds cuisineSectionIds: $cuisineSectionIds categorySectionIds: $categorySectionIds gate: $gate saved: $saved launchDarklyContext: $launchDarklyContext} ) { totalCount pageInfo { ... on PageInfo { endCursor startCursor hasNextPage } } nodes { __typename ...postGuide ...postReview ...postFeature ...postGuidebook ...postCollection } resultsProperties { hasExactMatch hasFuzzyMatch hasExactInterceptedTags hasFuzzyInterceptedTags hasInterceptedTagResults } } } fragment postGuide on PostGuide { ...post } fragment post on Post { __typename image { ...image } id canonicalPath slug title type updatedAt publishedAt categoryIds categories { name id displayName path } cuisineIds cuisines { name id displayName path } neighborhoodIds neighborhoods { __typename name id displayName path } contributors { image { ...image } name slug title } cuisines { __typename name id displayName path } preview } fragment image on Image { cloudinary { publicId height width } } fragment postReview on PostReview { ...post placeLocation { latitude longitude } placeName placeAddressStreet placeAddressZipcode placeAddressCity placeAddressState placePrice placeReservationPlatform placeReservationUrl placeChaseSapphireReservationUrl placePhone rating } fragment postFeature on PostFeature { ...post } fragment postGuidebook on PostGuidebook { ...post } fragment postCollection on PostCollection { ...post }'
    variables = {
        "sectionIds": [
            section_id
        ],
        "first": 10,
        "searchType": "RECENTLY_PUBLISHED",
        "excludeReviewStatus": "NOT_VISITED",
        "after": "eyJjdXJzb3JUeXBlIjoiT0ZGU0VUIiwib2Zmc2V0IjowfQ=="
    }
    # after = base64.b64encode('{"cursorType":"OFFSET","offset":0}'.encode()).decode()
    headers =  {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "priority": "u=1, i",
        "referrer": "https://www.theinfatuation.com/",
        "sec-ch-ua": "\"Chromium\";v=\"130\", \"Microsoft Edge\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "x-api-key": "AIzaSyCumTysqrJqyXJFyBR1F2rfDyMSxWEDR6U"
    }
    gql_url = 'https://api.theinfatuation.com/graphql?query=' + quote_plus(gql_query) + '&variables=' + quote_plus(json.dumps(variables, separators=(',', ':')))
    gql_json = utils.get_url_json(gql_url, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post in gql_json['data']['postSearch']['nodes']:
        post_url = 'https://' + split_url.netloc + post['canonicalPath']
        if post['type'] == 'REVIEW':
            post_url += '/reviews'
        elif post['type'] == 'GUIDE':
            post_url += '/guides'
        elif post['type'] == 'FEATURE':
            post_url += '/features'
        else:
            logger.warning('unhandled post type {} in {}'.format(post['type'], url))
            continue
        post_url += '/' + post['slug']
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
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