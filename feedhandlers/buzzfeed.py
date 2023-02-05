import json, pytz, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(image, caption=True, width=1000):
    captions = []
    if caption:
        if image.get('description'):
            captions.append(re.sub(r'</?p>', '', image['description']))
    if image.get('attribution'):
        captions.append(image['attribution'])
    #height = int(image['images']['original']['height']) * width / int(image['images']['original']['width'])
    #img_src = utils.clean_url(image['images']['original']['url']) + '?resize={:.0f}:{:.0f}'.format(width, height)
    img_src = utils.clean_url(image['images']['original']['url']) + '?resize={}:*'.format(width)
    return utils.add_image(img_src, ' | '.join(captions))


def add_quiz(quiz, poll=None):
    quiz_html = ''
    for question in quiz['questions']:
        if len(question['answers']) % 2 == 0:
            # 2 x ?
            n = 2
            w = '50%'
        else:
            # 3 x ?
            n = 3
            w = '33%'

        quiz_html += '<table style="width:100%; padding:1em; border:1px solid black; border-radius:10px;"><tr><td colspan="{}" style="text-align:center;"><h2>'.format(n)
        if question.get('title'):
            quiz_html += question['title']
        elif question.get('header'):
            quiz_html += question['header']
        elif question['tile_metadata'].get('tile_text'):
            quiz_html += question['tile_metadata']['tile_text']
        quiz_html += '</h2></td>'

        for i, answer in enumerate(question['answers']):
            if i % n == 0:
                quiz_html += '</tr><tr>'
            quiz_html += '<td style="width:{}; text-align:center">'.format(w)
            if answer.get('image'):
                quiz_html += '<img src="{}" loading="lazy" width="200px" height="200px" style="object-fit: cover;"/>'.format(answer['image'])
            elif answer.get('media'):
                quiz_html += '<img src="{}" loading="lazy" width="200px" height="200px" style="object-fit: cover;"/>'.format(answer['media']['url'])
            elif answer.get('tile_metadata') and answer['tile_metadata'].get('tile_styles') and answer['tile_metadata']['tile_styles'].get('media'):
                quiz_html += '<img src="{}" loading="lazy" width="200px" height="200px" style="object-fit: cover;"/>'.format(answer['tile_metadata']['tile_styles']['media']['url'])
            if answer.get('text'):
                quiz_html += '<h4>{}</h4>'.format(answer['text'])
            elif answer.get('header'):
                quiz_html += '<h4>{}</h4>'.format(answer['header'])
            elif answer.get('tile_metadata') and answer['tile_metadata'].get('tile_text'):
                quiz_html += '<h4>{}</h4>'.format(answer['tile_metadata']['tile_text'])
            quiz_html += '</td>'
        quiz_html += '</tr>'

        if question.get('reveal'):
            quiz_html += '<tr><td colspan="{}"><details><summary>Answer:</summary><h4>{}</h4>'.format(n, question['reveal']['title'])
            if question['reveal'].get('description'):
                quiz_html += markdown(question['reveal']['description'])
            if question['reveal'].get('media'):
                if question['reveal']['media']['type'] == 'img':
                    img_src = utils.clean_url(question['reveal']['media']['url']) + '?resize=1000:*'
                    if question['reveal']['media'].get('credit'):
                        caption = question['reveal']['media']['credit']
                    else:
                        caption = ''
                    quiz_html += utils.add_image(img_src, caption)
                else:
                    logger.warning('unhandled quiz reveal media type ' + question['reveal']['media']['type'])
            quiz_html += '</details></td></tr>'
        quiz_html += '</table>'

    if poll:
        poll_data = utils.get_url_json('https://mango.buzzfeed.com/polls/service/aggregate/editorial/get?poll_id={}'.format(poll))
        if poll_data:
            total = 0
            for key, val in poll_data['data']['results'].items():
                total += val
            quiz_html += '<table style="width:100%; padding:1em; border:1px solid black; border-radius:10px;"><tr><td><details><summary><span style="font-size:1.5em; font-weight:bold;">Results</span></summary>'
            for i, answer in enumerate(question['answers']):
                quiz_html += '<h4>'
                if answer.get('text'):
                    quiz_html += answer['text']
                elif answer.get('header'):
                    quiz_html += answer['header']
                elif answer.get('tile_metadata') and answer['tile_metadata'].get('tile_text'):
                    quiz_html += answer['tile_metadata']['tile_text']
                quiz_html += ': <span style="font-size:1.5em; font-weight:bold;">{:.1f}%</span> ({} votes)</h4>'.format(100*poll_data['data']['results'][str(i)]/total, poll_data['data']['results'][str(i)])
            quiz_html += '</details></td></tr></table>'
    elif quiz.get('results'):
        quiz_html += '<table style="width:100%; padding:1em; border:1px solid black; border-radius:10px;"><tr><td><h3>Results</h3></td></tr>'
        for i, result in enumerate(quiz['results']):
            quiz_html += '<tr><td><details><summary>Result {}:</summary>'.format(i+1)
            if result.get('title'):
                quiz_html += '<h4>{}</h4>'.format(result['title'])
            if result.get('description'):
                quiz_html += '<p>{}</p>'.format(result['description'])
            if result.get('media'):
                quiz_html += utils.add_image(result['media']['url'], result['media']['credit'])
            quiz_html += '</details></td></tr>'
        quiz_html += '</table>'
    return quiz_html


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(el.string)


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None

    article_json = next_data['props']['pageProps']['buzz']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonical_url']
    item['title'] = article_json['title']

    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(int(article_json['published']))
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_est = datetime.fromtimestamp(int(article_json['last_updated']))
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['bylines']:
        authors.append(it['display_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for key in article_json['laser_tags'].keys():
        for k, val in article_json['laser_tags'][key].items():
            for it in val:
                item['tags'].append(it['tag_display_name'])
    if not item.get('tags'):
        del item['tags']

    item['_image'] = article_json['picture']
    item['content_html'] = ''

    if article_json.get('description_text'):
        item['summary'] = article_json['description_text']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    for i, buzz in enumerate(article_json['sub_buzzes']):
        buzz_html = ''
        if buzz.get('header'):
            if buzz.get('number'):
                item['content_html'] += '<h3>{}. {}</h3>'.format(buzz['number'], buzz['header'])
            else:
                item['content_html'] += '<h3>{}</h3>'.format(buzz['header'])

        if buzz['form'] == 'text':
            if buzz.get('description'):
                item['content_html'] += buzz['description']

        elif buzz['form'] == 'image':
            if article_json['format']['page_type'] == 'list' or article_json['format']['page_type'] == 'list_countup':
                buzz_html += add_image(buzz, False)
                if buzz.get('description'):
                    buzz_html += buzz['description']
            else:
                buzz_html += add_image(buzz, True)

        elif buzz['form'] == 'photo_set':
            for it in buzz['photo_set_collection']:
                buzz_html += add_image(it)

        elif buzz['form'] == 'video':
            if buzz['source'] == 'youtube':
                buzz_html += utils.add_embed(buzz['original_url'])
            else:
                logger.warning('unhandled video source {} in {}'.format(buzz['source'], item['url']))

        elif buzz['form'] == 'tweet':
            buzz_html += utils.add_embed(buzz['original_url'])

        elif buzz['form'] == 'embed' and buzz['source'] == 'instagram':
            buzz_html += utils.add_embed(buzz['original_url'])

        elif buzz['form'] == 'bfp' and buzz['format_name'] == 'client_embed':
            buzz_html += utils.add_embed(buzz['bfp_data']['data']['oembed_url'])

        elif buzz['form'] == 'section_divider':
            buzz_html = '<hr/>'
            if buzz.get('header'):
                buzz_html += '<h3>{}</h3>'.format(buzz['header'])
            if buzz.get('description'):
                buzz_html += buzz['description']

        elif buzz['form'] == 'correction':
            buzz_html += buzz['description']

        elif buzz['form'] == 'quiz':
            if buzz['type'] == 'poll':
                buzz_html += add_quiz(buzz, buzz['id'])
            else:
                buzz_html += add_quiz(buzz)

        elif buzz['form'] == 'bfp' and buzz['format_name'] == 'quiz':
            buzz_html += add_quiz(buzz['bfp_data']['data'])

        elif buzz['form'] == 'bfp' and re.search(r'newsletter_signup|related_links', buzz['format_name']):
            buzz_html = ''

        else:
            logger.warning('unhandled sub_buzz form {} in {}'.format(buzz['form'], item['url']))
            continue

        if re.search(r'\[INSERT {}\]'.format(i), item['content_html']):
            item['content_html'] = item['content_html'].replace('[INSERT {}]'.format(i), buzz_html)
        else:
            item['content_html'] += buzz_html

    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.buzzfeed.com/tech.xml',
             'https://www.buzzfeednews.com/news.xml']
    for url in feeds:
        get_feed({"url": url}, True)
