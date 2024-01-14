import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_datetime(date):
    if date.endswith('Z'):
        date = date.replace('Z', '+00:00')
    elif date.endswith('+0000'):
        date = date.replace('+0000', '+00:00')
    return datetime.fromisoformat(date)


def get_api_data(api_url):
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "apollographql-client-name": "kraken",
        "apollographql-client-version": "v0.23.3",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"115\", \"Chromium\";v=\"115\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.203"
    }
    return utils.get_url_json(api_url, headers=headers)


def get_video_data(slug, video_id=''):
    if video_id:
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=VideoPlayerProps&variables=%7B%22videoId%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22ef401f728f7976541dd0c9bd7e337fbec8c3cb4fec5fa64e3d733d838d608e34%22%7D%7D'.format(video_id)
        api_data = get_api_data(api_url)
        if not api_data:
            return None
        slug = api_data['data']['videoPlayerProps']['metadata']['slug']
    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Video&variables=%7B%22slug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%226ba07ded7512c10289193c935c7b1b63fb26b9baf890bb0b0685cd4f2e5d8e87%22%7D%7D'.format(slug)
    api_data = get_api_data(api_url)
    if not api_data:
        return None
    return api_data['data']['videoBySlug']


def get_article_data(slug):
    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Article&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22157c24c5c5cc427eb440fad7af987ca91b655f6348cb49524f3d7a66de2b5fd6%22%7D%7D'.format(slug)
    api_data = get_api_data(api_url)
    if not api_data:
        return None
    return api_data['data']['article']


def get_slideshow_data(slug, cursor=0, count=20):
    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Slideshow&variables=%7B%22queryBy%22%3A%22slug%22%2C%22value%22%3A%22{}%22%2C%22cursor%22%3A{}%2C%22count%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22a7c3d19c1b8a13cc00cc867594013648bb8be021c9609f481133b5837008f3f0%22%7D%7D'.format(slug, cursor, count)
    api_data = get_api_data(api_url)
    if not api_data:
        return None
    return api_data['data']['slideshow']


def get_slideshow_content(url, args, site_json, save_debug):
    if url.startswith('https:'):
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        if paths[0] != 'slideshows' or len(paths) < 2:
            logger.warning('unhandled video url ' + url)
            return None
        slug = paths[1]
    else:
        slug = url

    slideshow_json = get_slideshow_data(slug)
    if not slideshow_json:
        return None
    if save_debug:
        utils.write_file(slideshow_json, './debug/slideshow.json')
    content_json = slideshow_json['content']

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

    item['author'] = {}
    if content_json.get('contributors'):
        authors = []
        for it in content_json['contributors']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'IGN Slideshow'

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['_image'] = slideshow_json['slideshowImages']['images'][0]['url'] + '?width=1000'

    n = 1
    total = slideshow_json['slideshowImages']['pageInfo']['total']
    cursor = slideshow_json['slideshowImages']['pageInfo']['nextCursor']
    item['content_html'] = ''

    if 'embed' in args:
        link = '{}/content?read&url={}'.format(config.server, quote_plus(item['url']))
        caption = '<a href="{}">View slideshow: {} ({} images)</a>'.format(item['url'], item['title'], total)
        item['content_html'] = utils.add_image(item['_image'], caption, link=link)
        return item

    while n <= total:
        if not slideshow_json:
            slideshow_json = get_slideshow_data(slug, cursor, 20)
            if not slideshow_json:
                break
            cursor = slideshow_json['slideshowImages']['pageInfo']['nextCursor']
            total = slideshow_json['slideshowImages']['pageInfo']['total']
        for image in slideshow_json['slideshowImages']['images']:
            caption = '{} of {}'.format(n, total)
            if image.get('caption'):
                caption += ': {}'.format(image['caption'])
            item['content_html'] += utils.add_image(image['url'] + '?width=1000', caption)
            item['content_html'] += '<div>&nbsp;</div>'
            n += 1
        slideshow_json = None
    return item


def get_video_content(url, args, site_json, save_debug=False):
    if url.startswith('https:'):
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        if paths[0] != 'videos' or len(paths) < 2:
            logger.warning('unhandled video url ' + url)
            return None
        slug = paths[1]
    else:
        slug = url

    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Video&variables=%7B%22slug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%226ba07ded7512c10289193c935c7b1b63fb26b9baf890bb0b0685cd4f2e5d8e87%22%7D%7D'.format(slug)
    api_data = get_api_data(api_url)
    if not api_data:
        return None
    video_json = api_data['data']['videoBySlug']
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
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

    item['author'] = {}
    if content_json.get('contributors'):
        authors = []
        for it in content_json['contributors']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'IGN Videos'

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['_image'] = content_json['feedImage']['url'] + '?width=1000'

    caption = '<a href="{}">Watch: {}</a>'.format(item['url'], item['title'])

    item['content_html'] = ''
    if content_json.get('subtitle') and 'embed' not in args:
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['subtitle'])

    video = None
    if video_json.get('assets'):
        videos = []
        for it in video_json['assets']:
            if it['__typename'] == 'VideoAsset' and it.get('height'):
                videos.append(it)
        if videos:
            video = utils.closest_dict(video_json['assets'], 'height', 480)
            item['content_html'] += utils.add_video(video['url'], 'video/mp4', item['_image'], caption)
    if not video and video_json.get('videoMetadata') and video_json['videoMetadata'].get('m3uUrl'):
        item['content_html'] += utils.add_video(video_json['videoMetadata']['m3uUrl'], 'application/x-mpegURL', item['_image'], caption)

    if video_json.get('videoMetadata') and video_json['videoMetadata'].get('descriptionHtml'):
        item['summary'] = video_json['videoMetadata']['descriptionHtml']
        if 'embed' not in args:
            item['content_html'] += item['summary']
    return item


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

    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Article&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22157c24c5c5cc427eb440fad7af987ca91b655f6348cb49524f3d7a66de2b5fd6%22%7D%7D'.format(paths[1])
    api_data = get_api_data(api_url)
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

    item['author'] = {}
    if content_json.get('contributors'):
        authors = []
        for it in content_json['contributors']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'IGN'

    item['tags'] = []
    if content_json.get('contentCategory'):
        item['tags'].append(content_json['contentCategory']['name'])
    if content_json.get('attributes'):
        for it in content_json['attributes']:
            item['tags'].append(it['attribute']['name'])

    item['content_html'] = ''
    if content_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['subtitle'])

    if article_json.get('article') and article_json['article'].get('heroVideoContentSlug'):
        video_item = get_video_content(article_json['article']['heroVideoContentSlug'], {"embed": True}, site_json, False)
        if video_item:
            item['content_html'] += video_item['content_html']
    elif content_json.get('headerImageUrl'):
        item['_image'] = content_json['headerImageUrl'] + '?width=1000'
        item['content_html'] += utils.add_image(item['_image'])
    elif content_json.get('feedImage') and content_json['feedImage']['__typename'] == 'Image':
        item['_image'] = content_json['feedImage']['url'] + '?width=1000'
        item['content_html'] += utils.add_image(item['_image'])

    if article_json.get('review'):
        item['summary'] = article_json['review']['verdict']
    elif article_json.get('excerpt'):
        item['summary'] = content_json['excerpt']

    # page_html = ''
    # for html in content_json['paginatedHtmlPage']:
    #     page_html += html
    #page_soup = BeautifulSoup(page_html, 'html.parser')

    if article_json.get('article'):
        page_soup = BeautifulSoup(article_json['article']['processedHtml'], 'html.parser')

    for el in page_soup.find_all('aside'):
        el.decompose()

    for el in page_soup.find_all('section'):
        if el.get('data-transform'):
            if re.search(r'commerce-deal|mobile-ad-break|object-feedback|poll', el['data-transform']):
                el.decompose()

            elif el['data-transform'] == 'image-with-caption':
                el_html = utils.add_image(el['data-image-url'], el['data-image-title'])
                el.insert_after(BeautifulSoup(el_html, 'html.parser'))
                el.decompose()

            elif el['data-transform'] == 'slideshow':
                slideshow_item = get_slideshow_content(el['data-slug'], {"embed": True}, site_json, save_debug)
                if slideshow_item:
                    el.insert_after(BeautifulSoup(slideshow_item['content_html'], 'html.parser'))
                    el.decompose()
                else:
                    logger.warning('unable to get slideshow data for ' + el['data-slug'])

            elif el['data-transform'] == 'ignvideo':
                video_item = get_video_content(el['data-slug'], {"embed": True}, site_json, False)
                if video_item:
                    el.insert_after(BeautifulSoup(video_item['content_html'], 'html.parser'))
                    el.decompose()
                else:
                    logger.warning('unable to get video data for ' + el['data-slug'])

            elif el['data-transform'] == 'quoteBox':
                el_html = utils.add_pullquote(el.get_text())
                el.insert_after(BeautifulSoup(el_html, 'html.parser'))
                el.decompose()

            elif el['data-transform'] == 'divider':
                el.insert_after(BeautifulSoup('<hr style="width:80%;"/>', 'html.parser'))
                el.decompose()

            else:
                logger.warning('unhandled section data-transform={} in {}'.format(el['data-transform'], url))

    for el in page_soup.find_all('a'):
        if re.search(r'\.(gif|jpg|jpeg|png)$', el['href'], flags=re.I):
            el.insert_after(BeautifulSoup(utils.add_image(el['href'] + '?width=1000'), 'html.parser'))
            el.decompose()

    for el in page_soup.find_all('blockquote', class_='twitter-tweet'):
        tweet_url = el.find_all('a')[-1]['href']
        if re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url):
            el.insert_after(BeautifulSoup(utils.add_embed(tweet_url), 'html.parser'))
            el.decompose()

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
    # if not lead and item.get('_image'):
    #     item['content_html'] += utils.add_image(item['_image'])

    verdict = ''
    if article_json.get('review'):
        if article_json['review']['editorsChoice'] == True:
            editors_choice = '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        else:
            editors_choice = ''
        item['content_html'] += '<br/><div><div style="text-align:center">{}<h1 style="margin:0;">{}</h1>{}</div><p><em>{}</em></p><div style="font-size:0.8em;"><ul>'.format(editors_choice, article_json['review']['score'], article_json['review']['scoreText'].upper(), article_json['review']['scoreSummary'])

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
                                    date = utils.format_display_date(dt, False)
                                else:
                                    date = 'N/A'
                                if not releases.get(date):
                                    releases[date] = []
                                if release.get('platformAttributes'):
                                    for it in release['platformAttributes']:
                                        if it['name'] not in releases[date]:
                                            releases[date].append(it['name'])
                            for key, val in releases.items():
                                item['content_html'] += '<li>Released {}</li>'.format(key)
                                if val:
                                    item['content_html'] += ' for {}'.format(', '.join(val))
                                item['content_html'] += '</li>'

                for key, val in object.items():
                    if isinstance(val, list):
                        attrs = []
                        for it in val:
                            if it['__typename'] == 'Attribute':
                                attrs.append(it['name'])
                                #item['tags'].append(it['name'])
                        if attrs:
                            item['content_html'] += '<li>{}: {}</li>'.format(key.capitalize(), ', '.join(attrs))

        item['content_html'] += '</ul></div></div><hr style="width:80%;"/>'
        verdict = '<h2>Verdict</h2><p>{}</p>'.format(article_json['review']['verdict'])

    if verdict:
        page_soup.append(BeautifulSoup(verdict, 'html.parser'))

    item['content_html'] += str(page_soup)

    if not item.get('tags'):
        del item['tags']
    return item


def get_feed(url, args, site_json, save_debug=False):
    headers = {"apollographql-client-name": "kraken",
               "apollographql-client-version": "v0.23.5",
               "content-type": "application/json",
               "x-postgres-articles": "true"}

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=HomepageContentFeed&variables=%7B%22filter%22%3A%22Latest%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A12%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%228e11ab9cbe6f6280abc0f030db519070c11ef3c1b6911d33a83d6462c461bf8d%22%7D%7D'
        data_keys = ['homepage', 'contentFeed', 'feedItems']

    elif paths[0] == 'news':
        if len(paths) > 1:
            if paths[1] == 'tv':
                feed_filter = 'TV'
            elif paths[1] == 'playstation':
                feed_filter = 'PlayStation'
            else:
                feed_filter = paths[1].captialize()
        else:
            feed_filter = 'Latest'
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=HomepageContentFeed&variables=%7B%22filter%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%2C%22newsOnly%22%3Atrue%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%228e11ab9cbe6f6280abc0f030db519070c11ef3c1b6911d33a83d6462c461bf8d%22%7D%7D'.format(feed_filter)
        data_keys = ['homepage', 'contentFeed', 'feedItems']

    elif paths[0] == 'reviews' or paths[0] == 'editors-choice':
        # review/editors-choice, filter, platform/genre
        if paths[0] == 'editors-choice':
            editors_choice = 'true'
        else:
            editors_choice = 'false'
        platform = 'null'
        feed_filter = 'All'
        genre = 'null'
        if len(paths) > 1:
            if paths[1] == 'tv':
                feed_filter = 'TV'
            else:
                feed_filter = paths[1].capitalize()
            if paths[1] == 'games' and len(paths) == 3:
                platform = '%5B%22{}%22%5D'.format(paths[2])
        # Genre isn't recognized as a url query parameter, but it's not rejected either
        # So if included we can parse it for the GraphQL query
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('genre'):
                genre = '%5B%22{}%22%5D'.format(query['genre'][0])
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ReviewsContentFeed&variables=%7B%22filter%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%2C%22editorsChoice%22%3A{}%2C%22sortOption%22%3A%22Latest%22%2C%22gamePlatformSlugs%22%3A{}%2C%22genreSlugs%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22b6e9c5db3b03ea9b7fdd936e0bc77ed45db6e5ede32a205fce4fb01a284cfb64%22%7D%7D'.format(feed_filter, editors_choice, platform, genre)
        data_keys = ['reviewContentFeed', 'feedItems']

    elif paths[0] == 'videos':
        feed_filter = 'Videos'
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('filter'):
                feed_filter = query['genre'][0].capitalize()
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ChannelContentFeed&variables=%7B%22slug%22%3A%22videos%22%2C%22region%22%3A%22us%22%2C%22filter%22%3A%22{}%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%220dc7de16d185896e2f1cb4c5eecf42ee8dfc0b23200f0c79b072d9516688d967%22%7D%7D'
        data_keys = ['channel', 'contentFeed', 'feedItems']

    elif paths[0] == 'person':
        # Get authorId
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=AuthorInfo&variables=%7B%22nickname%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22d948c36fe858c1f89242f06dad0bff8f5ad8ba0a472a67aefb74e1f9858f0030%22%7D%7D'.format(paths[1])
        api_data = utils.get_url_json(api_url, headers=headers)
        if not api_data:
            return None
        if len(paths) > 2:
            feed_filter = paths[2].capitalize()
        else:
            feed_filter = 'Latest'
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=AuthorContentFeed&variables=%7B%22authorId%22%3A{}%2C%22filter%22%3A%22{}%22%2C%22count%22%3A10%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2200032d017178015ed43cbfeab79daee8c9e4a1014ba88ac208c5aa3b07baebde%22%7D%7D'.format(api_data['data']['author']['authorId'], feed_filter)
        data_keys = ['contributor', 'contentFeed', 'feedItems']

    else:
        feed_filter = 'All'
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('filter'):
                feed_filter = query['filter'][0].capitalize()
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ChannelContentFeed&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22filter%22%3A%22{}%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%220dc7de16d185896e2f1cb4c5eecf42ee8dfc0b23200f0c79b072d9516688d967%22%7D%7D'.format(paths[0], feed_filter)
        data_keys = ['channel', 'channelFeed', 'feedItems']

    api_data = utils.get_url_json(api_url, headers=headers)
    if not api_data:
        return None
    if save_debug:
        utils.write_file(api_data, './debug/feed.json')

    content_items = api_data['data']
    for key in data_keys:
        content_items = content_items[key]

    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    for it in content_items:
        if it['__typename'] == 'ModernArticle':
            url = 'https://www.ign.com' + it['content']['url']
            date = it['content']['publishDate']
        elif it['__typename'] == 'Video':
            url = 'https://www.ign.com' + it['url']
            date = it['publishDate']
        else:
            logger.warning('unhandled content type ' + it['__typename'])
            continue
        if save_debug:
            logger.debug('getting content from ' + url)
        if 'age' in args:
            dt = get_datetime(date)
            item = {}
            item['_timestamp'] = dt.timestamp()
            if not utils.check_age(item, args):
                if save_debug:
                    logger.debug('skipping old article ' + url)
                continue
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = items.copy()
    return feed
