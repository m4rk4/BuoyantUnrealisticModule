import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import twitter

import logging
logger = logging.getLogger(__name__)

def get_content_html(content_uri):
  # Skip these
  if re.search(r'\/(magazine-issue-tout|newsletter-flex-text|related|single-related-story)\/', content_uri):
    return ''

  # Handle these without loading the content_uri
  if '/divider/' in content_uri:
    return '<hr width="80%" />'

  content_html = ''
  content_json = utils.get_url_json('https://' + content_uri)
  if content_json:
    if '/clay-paragraph/' in content_uri:
      content_html = '<p>{}</p>'.format(content_json['text'])

    elif '/clay-subheader/' in content_uri:
      #content_html = '<hr width="80%"><h3>{}</h3>'.format(content_json['text'])
      content_html = '<h3>{}</h3>'.format(content_json['text'])

    elif '/image/' in content_uri or '/image-sequence-item/' in content_uri:
      caption = []
      if content_json.get('imageCaption'):
        caption.append(content_json['imageCaption'].strip())
      if content_json.get('imageType'):
        caption.append(content_json['imageType'].strip() + ':')
      if content_json.get('imageCredit'):
        caption.append(content_json['imageCredit'].strip())
      content_html = utils.add_image(content_json['imageUrl'], ' '.join(caption))

    elif '/image-sequence/' in content_uri:
      for image in content_json['images']:
        content_html += get_content_html(image['_ref'])

    elif '/image-collection/' in content_uri:
      for image in content_json['imageCollection']:
        caption = []
        if image.get('imageCaption'):
          caption.append(image['imageCaption'].strip())
        if image.get('imageType'):
          caption.append(image['imageType'].strip() + ':')
        if image.get('imageCredit'):
          caption.append(image['imageCredit'].strip())
        else:
          if content_json['imageCollection'][-1].get('imageCredit'):
            caption.append(content_json['imageCollection'][-1]['imageCredit'].strip())
        content_html = utils.add_image(image['imageUrl'], ' '.join(caption))

    elif '/video/' in content_uri:
      if content_json.get('youtubeId'):
        content_html = utils.add_youtube(content_json['youtubeId'])
      else:
        logger.warning('unhandled video content in https://' + content_uri)

    elif '/blockquote/' in content_uri:
      soup = BeautifulSoup(content_json['text'], 'html.parser')
      if soup:
        for p in soup.find_all('p'):
          p.unwrap()
        text = str(soup)
        text = text.replace('<br/>', '<br/><br/>')
        content_html = utils.add_blockquote(text)
      else:
        content_html = utils.add_blockquote(content_json['text'])

    elif '/pull-quote/' in content_uri:
      text = content_json['quote']
      if content_json.get('attribution'):
        text += '<br />&mdash;&nbsp;{}'.format(content_json['attribution'])
      content_html = utils.add_pullquote(text)

    elif '/source-links/' in content_uri:
      for src in content_json['content']:
        text = []
        if src.get('title'):
          text.append(src['title'])
        if src.get('publication'):
          text.append(src['publication'])
        content_html = '<p>Source: <a href="{}">{}</a></p>'.format(src['url'], ' '.join(text))

    elif '/clay-tweet/' in content_uri:
      tweet = twitter.get_content(content_json['tweetId'], None)
      content_html = tweet['content_html']

    elif '/subsection/' in content_uri:
      content_html = ''
      if content_json['borders']['top'] == True:
        content_html += '<hr width="80%">'
      if content_json.get('title'):
        content_html += '<h4>{}</h4>'.format(content_json['title'])
      for content in content_json['content']:
        content_html += get_content_html(content['_ref'])
      if content_json['borders']['bottom'] == True:
        content_html += '<hr width="80%">'

    elif '/product/' in content_uri:
      caption = []
      if content_json.get('imageCaption'):
        caption.append(content_json['imageCaption'].strip())
      if content_json.get('imageType'):
        caption.append(content_json['imageType'].strip() + ':')
      if content_json.get('imageCredit'):
        caption.append(content_json['imageCredit'].strip())
      content_html = utils.add_image(content_json['dynamicProductImage']['url'], ' '.join(caption))
      content_html += '<h4>{}</h4>'.format(content_json['agora']['name'])
      for desc in content_json['description']:
        content_html += get_content_html(desc['_ref'])
      content_html += '<ul>'
      for merch in content_json['agora']['merchants']:
        content_html += '<li><a href="{}">{}</a>: ${}</li>'.format(utils.clean_referral_link(merch['buyUrl']), merch['name'], merch['price'])
      content_html += '</ul>'
    else:
      logger.warning('unhandled content in https://' + content_uri)

  return content_html

def get_content(url, args, save_debug=False, page_uri=''):
  item = {}

  if not page_uri:
    article_html = utils.get_url_html(url)
    if article_html:
      soup = BeautifulSoup(article_html, 'html.parser')
      page_uri = soup.html['data-uri']
  
  if page_uri:
    article_uri = ''
    page_json = utils.get_url_json('https://' + page_uri)
    if page_json:
      for page in page_json['main']:
        if '/article/' in page:
          article_uri = page
          break

  if article_uri:
    article_json = utils.get_url_json('https://' + article_uri)
    if article_json:
      if save_debug:
        with open('./debug/debug.json', 'w') as file:
          json.dump(article_json, file, indent=4)

      item['id'] = article_uri
      item['url'] = article_json['canonicalUrl']
      item['title'] = article_json['pageTitle']

      dt = datetime.fromisoformat(article_json['date']).astimezone(timezone.utc)
      item['date_published'] = dt.isoformat()
      item['_timestamp'] = dt.timestamp()
      item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

      # Check age
      if 'age' in args:
        if not utils.check_age(item, args):
          return None

      authors = []
      for author in article_json['authors']:
        authors.append(author['text'])
      item['author'] = {}
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

      tags_json = utils.get_url_json('https://' + article_json['tags']['_ref'])
      if tags_json:
        item['tags'] = []
        for it in tags_json['items']:
          item['tags'].append(it['text'])
      else:
        item['tags'] = article_json['normalizedTags'].copy()

      item['summary'] = article_json['pageDescription']

      item['content_html'] = ''

      if article_json.get('ledeUrl'):
        item['_image'] = article_json['ledeUrl']
        caption = []
        if article_json.get('ledeCaption'):
          caption.append(article_json['ledeCaption'].strip())
        if article_json.get('ledeImageType'):
          caption.append(article_json['ledeImageType'].strip() + ':')
        if article_json.get('ledeCredit'):
          caption.append(article_json['ledeCredit'].strip())
        item['content_html'] += utils.add_image(article_json['ledeUrl'], ' '.join(caption))

      for content in article_json['content']:
        item['content_html'] += get_content_html(content['_ref'])

  return item

def get_feed(args, save_debug=False):
  feed = utils.init_jsonfeed(args)
  feed_items = None
  feed_json = utils.get_url_json('https://nymag.com/_components/nymag-latest-feed/instances/index@published')
  if feed_json:
    for site in feed_json['tabs']:
      if site['moreUrl'] in args['url']:
        feed_items = site['articles']
  if feed_items:
    n = 0
    items = []
    for feed_item in feed_items:
      if feed_item.get('type') and feed_item['type'] == 'external':
        continue
      url = feed_item['canonicalUrl'].replace('http://', 'https://')
      if save_debug:
        logger.debug('getting content for ' + url)
      item = get_content(url, args, save_debug, feed_item['pageUri'])
      if item:
        if utils.filter_item(item, args) == True:
          items.append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
    feed['items'] = items.copy()
  return feed