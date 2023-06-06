import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_datetime(date):
    if date.endswith('Z'):
        date = date.replace('Z', '+00:00')
    elif date.endswith('+0000'):
        date = date.replace('+0000', '+00:00')
    return datetime.fromisoformat(date)

def get_video_data(slug, video_id=''):
    if video_id:
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=VideoPlayerProps&variables=%7B%22videoId%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22ef401f728f7976541dd0c9bd7e337fbec8c3cb4fec5fa64e3d733d838d608e34%22%7D%7D'.format(video_id)
        api_data = utils.get_url_json(api_url)
        if not api_data:
            return None
        slug = api_data['data']['videoPlayerProps']['metadata']['slug']

    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Video&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22689efcbe89287bd0f561caf42a9ab1e3abb4f09e7aa2937ed367ac1683ecd5d2%22%7D%7D'.format(slug)
    api_data = utils.get_url_json(api_url)
    if not api_data:
        return None
    return api_data['data']['video']


def get_article_data(slug):
    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ArticleInfo&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2273f4f09a3aab27ad84ed9b663e2690a31a466bbe21735e6529878bb8f7bbcd82%22%7D%7D'.format(slug)
    api_data = utils.get_url_json(api_url)
    if not api_data:
        return None
    return api_data['data']['articleBySlug']


def get_slideshow_data(slug, cursor=0, count=20):
    api_url = 'https://mollusk.apis.ign.com/graphql?operationName=Slideshow&variables=%7B%22queryBy%22%3A%22slug%22%2C%22value%22%3A%22{}%22%2C%22cursor%22%3A{}%2C%22count%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%224f2cca55bc379f45459bf6218622608444270d7b1367e7ae29de6955edc98404%22%7D%7D'.format(slug, cursor, count)
    api_data = utils.get_url_json(api_url)
    if not api_data:
        return None
    return api_data['data']['slideshow']


def get_slideshow_content(slug, args, site_json, save_debug):
    slideshow_json = get_slideshow_data(slug)
    if not slideshow_json:
        return None
    if save_debug:
        utils.write_file(slideshow_json, './debug/slideshow.json')
    item = {}
    item['id'] = slideshow_json['content']['id']
    item['url'] = '{}/content?read&url=https%3A%2F%2Fwww.ign.com%2Fslideshow%2F{}'.format(config.server, slug)
    total = slideshow_json['slideshowImages']['pageInfo']['total']
    item['title'] = '{} ({} images)'.format(slideshow_json['content']['title'], total)
    dt = get_datetime(slideshow_json['content']['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    item['author'] = {"name": "IGN"}
    item['_image'] = slideshow_json['slideshowImages']['images'][0]['url']
    item['content_html'] = ''
    next = slideshow_json['slideshowImages']['pageInfo']['nextCursor']
    n = 1
    while n <= total:
        if not slideshow_json:
            slideshow_json = get_slideshow_data(slug, next, 20)
            if not slideshow_json:
                break
            next = slideshow_json['slideshowImages']['pageInfo']['nextCursor']
        total = slideshow_json['slideshowImages']['pageInfo']['total']
        for image in slideshow_json['slideshowImages']['images']:
            caption = '[{}/{}] '.format(n, total)
            item['content_html'] += utils.add_image(image['url'] + '?width=1000', caption)
            if image.get('caption'):
                item['content_html'] += '<p>{}</p>'.format(image['caption'])
            item['content_html'] += '<br/>'
            n += 1
        slideshow_json = None
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] == 'articles':
        page_json = get_article_data(paths[1])
    elif paths[0] == 'videos':
        page_json = get_video_data(paths[1])
    elif paths[0] == 'slideshow':
        return get_slideshow_content(paths[1], args, site_json, save_debug)
    else:
        logger.warning('unhandled url ' + url)
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    item['id'] = page_json['id']
    item['url'] = url
    item['title'] = page_json['title']

    dt = get_datetime(page_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if page_json.get('modifiedDate'):
        dt = get_datetime(page_json['modifiedDate'])
        item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['author'] = {}
    if page_json.get('authorSocialDetails'):
        authors = []
        for author in page_json['authorSocialDetails']:
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        if page_json['__typename'] == 'Video':
            item['author']['name'] = 'IGN Videos'
        else:
            item['author']['name'] = 'IGN'

    item['tags'] = []
    if page_json.get('tagSlugs'):
        item['tags'] = page_json['tagSlugs'].copy()
    elif page_json.get('tags'):
        for tag in page_json['tags']:
            if isinstance(tag, str):
                item['tags'].append(tag)
            elif isinstance(tag, dict):
                item['tags'].append(tag['displayName'])
    if page_json.get('categories'):
        for tag in page_json['categories']:
            if isinstance(tag, str):
                item['tags'].append(tag)
            elif isinstance(tag, dict):
                item['tags'].append(tag['displayName'])

    item['_image'] = page_json['thumbnailUrl'] + '?width=1000'

    if page_json['__typename'] == 'Video':
        item['summary'] = page_json['description']
        video = utils.closest_dict(page_json['assets'], 'width', 640)
        item['_video'] = video['url']
        poster = page_json['thumbnailUrl'] + '?width=1000'
        item['content_html'] = utils.add_video(video['url'], 'video/mp4', poster)
        item['content_html'] += '<p>{}</p>'.format(page_json['description'])
        return item

    if page_json.get('review'):
        item['summary'] = page_json['review']['verdict']
    else:
        item['summary'] = page_json['promoSummary']

    page_html = ''
    for html in page_json['paginatedHtmlPage']:
        page_html += html

    page_soup = BeautifulSoup(page_html, 'html.parser')
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
                slideshow = get_slideshow_content(el['data-slug'], {}, site_json, save_debug)
                if slideshow:
                    el_html = '<h3 class="slideshow">Slideshow: <a href="{}">{}</a></h3>'.format(slideshow['url'], slideshow['title'])
                    el_html += utils.add_image(slideshow['_image'], link=slideshow['url']) + '<br/>'
                    el.insert_after(BeautifulSoup(el_html, 'html.parser'))
                el.decompose()

            elif el['data-transform'] == 'ignvideo':
                video_json = get_video_data(el['data-slug'])
                if video_json:
                    poster = video_json['thumbnailUrl'] + '?width=1000'
                    caption = video_json['title']
                    video = utils.closest_dict(video_json['assets'], 'width', 640)
                    el_html = utils.add_video(video['url'], 'video/mp4', poster, caption)
                    el.insert_after(BeautifulSoup(el_html, 'html.parser'))
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

    item['content_html'] = ''
    lead = False
    if page_json.get('headerImageUrl'):
        item['content_html'] += utils.add_image(page_json['headerImageUrl'] + '?width=1000')
        lead = True
    elif page_json.get('canWatchRead') and page_json['canWatchRead'] == True and page_json.get('relatedMediaId'):
        # Use the associated video as the lead (usually for reviews)
        video_json = get_video_data('', page_json['relatedMediaId'])
        if video_json:
            poster = video_json['thumbnailUrl'] + '?width=1000'
            caption = video_json['title']
            video = utils.closest_dict(video_json['assets'], 'width', 640)
            item['content_html'] += utils.add_video(video['url'], 'video/mp4', poster, caption)
            lead = True
    if not lead:
        item['content_html'] += utils.add_image(item['_image'])

    verdict = ''
    is_review = False
    if page_json.get('review'):
        for key, value in page_json['review'].items():
            if key != '__typename' and value:
                is_review = True
                break

    if is_review:
        if page_json['review']['editorsChoice'] == True:
            editors_choice = '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        else:
            editors_choice = ''
        item['content_html'] += '<br/><div><div style="text-align:center">{}<h1 style="margin:0;">{}</h1>{}</div><p><em>{}</em></p><div style="font-size:0.8em;"><ul>'.format(editors_choice, page_json['review']['score'], page_json['review']['scoreText'].upper(), page_json['review']['scoreSummary'])

        if page_json['object'].get('objectRegions'):
            object = page_json['object']['objectRegions'][0]
            if object.get('ageRating'):
                desc = []
                if object.get('ageRatingDescriptors'):
                    for it in object['ageRatingDescriptors']:
                        desc.append(it['name'])
                if desc:
                    item['content_html'] += '<li>Rating: {} ({})</li>'.format(object['ageRating']['name'], ', '.join(desc))
                    item['tags'] += desc
                else:
                    item['content_html'] += '<li>Rating: {}</li>'.format(object['ageRating']['name'])

            if object.get('releases'):
                platforms = []
                for it in object['releases']:
                    if it.get('platformAttributes'):
                        platforms.append(it['platformAttributes'][0]['name'])
                if platforms:
                    item['content_html'] += '<li>Platforms: {}</li>'.format(', '.join(platforms))
                item['tags'] += platforms

                if object['releases'][0].get('timeframeYear'):
                    item['content_html'] += '<li>Release date: {}</li>'.format(object['releases'][0]['timeframeYear'])
                elif object['releases'][0].get('date'):
                    dt = get_datetime(object['releases'][0]['date'])
                    item['content_html'] += '<li>Release date: {}</li>'.format(utils.format_display_date(dt, False))

        for key, val in page_json['object'].items():
            if isinstance(val, list):
                attrs = []
                for it in val:
                    if it['__typename'] == 'Attribute':
                        attrs.append(it['name'])
                        item['tags'].append(it['name'])
                if attrs:
                    item['content_html'] += '<li>{}: {}</li>'.format(key.capitalize(), ', '.join(attrs))

        item['content_html'] += '</ul></div></div><hr style="width:80%;"/>'
        verdict = '<h2>Verdict</h2><p>{}</p>'.format(page_json['review']['verdict'])

    if verdict:
        page_soup.append(BeautifulSoup(verdict, 'html.parser'))

    item['content_html'] += str(page_soup)

    if not item.get('tags'):
        del item['tags']
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=HomepageContentFeed&variables=%7B%22filter%22%3A%22Latest%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A12%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22181bfd3ccd2365e75755882430f2da42a663c2ea8c2f198c33a5562ea50fadfd%22%7D%7D'
        data_keys = ['homepage', 'contentFeed', 'contentItems']

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
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=NewsContentFeed&variables=%7B%22filter%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%2C%22newsOnly%22%3Atrue%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2213bef5508c5f2d4610f93df7c872b8a362cb0dae29eba4e4804eb11809e77760%22%7D%7D'.format(feed_filter)

        data_keys = ['homepage', 'contentFeed', 'contentItems']

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
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ReviewsContentFeed&variables=%7B%22filter%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%2C%22editorsChoice%22%3A{}%2C%22sortOption%22%3A%22Latest%22%2C%22gamePlatformSlugs%22%3A{}%2C%22genreSlugs%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22664109766601448c3c393755d2234600e55000cfb760ad0d7200fdc1322c2adb%22%7D%7D'.format(feed_filter, editors_choice, platform, genre)
        data_keys = ['reviewContentFeed', 'contentItems']

    elif paths[0] == 'videos':
        feed_filter = 'Videos'
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('filter'):
                feed_filter = query['genre'][0].capitalize()
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ChannelContentFeed&variables=%7B%22slug%22%3A%22videos%22%2C%22region%22%3A%22us%22%2C%22filter%22%3A%22{}%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2210ffadcad21ceaa24ec9d252d60adbffd740f02165feb0ede135d745769161eb%22%7D%7D'.format(feed_filter)
        data_keys = ['channel', 'contentFeed', 'contentItems']

    elif paths[0] == 'person':
        if len(paths) > 2:
            feed_filter = paths[2].capitalize()
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=AuthorMoreReviewsFeed&variables=%7B%22authorId%22%3A4917321%2C%22filter%22%3A%22{}%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%2C%22region%22%3A%22us%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22d2af4f25b9e6f73f4f2880e5c193f23e0cfae1240356feef992a7082a5b0b49e%22%7D%7D'.format(feed_filter)
        data_keys = ['author', 'contentFeed', 'contentItems']

    else:
        feed_filter = 'All'
        if split_url.query:
            query = parse_qs(split_url.query)
            if query.get('filter'):
                feed_filter = query['filter'][0].capitalize()
        api_url = 'https://mollusk.apis.ign.com/graphql?operationName=ChannelContentFeed&variables=%7B%22slug%22%3A%22{}%22%2C%22region%22%3A%22us%22%2C%22filter%22%3A%22{}%22%2C%22startIndex%22%3A0%2C%22count%22%3A10%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2210ffadcad21ceaa24ec9d252d60adbffd740f02165feb0ede135d745769161eb%22%7D%7D'.format(paths[0], feed_filter)
        data_keys = ['channel', 'channelFeed', 'contentItems']

    headers = {"apollographql-client-name": "kraken",
               "apollographql-client-version": "v0.11.19",
               "content-type": "application/json",
               "x-postgres-articles": "true"}
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


