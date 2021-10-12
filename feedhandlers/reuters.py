import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import fusion
import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(image_item, width_target):
  images = []
  for key, val in image_item['renditions']['original'].items():
    image = {}
    image['width'] = int(key[:-1])
    image['url'] = val
    images.append(image)
  image = utils.closest_dict(images, 'width', width_target)
  return image['url']

def get_investigates_content(url, args, save_debug):
  content = utils.get_url_content(url)
  if not content:
    return None

  article_content = content.decode('utf-8')
  soup = BeautifulSoup(article_content, 'html.parser')
  article = soup.find('article')
  if not article:
    return None

  item = {}
  item['id'] = article['id']
  item['url'] = url
  item['title'] = soup.title.string

  el = article.find('time')
  if el:
    dt = datetime.fromisoformat(el['datetime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    # Check age
    if 'age' in args:
      if not utils.check_age(item, args):
        return None

  el = article.find(class_='byline')
  if el:
    authors = []
    for it in el.find_all('a'):
      authors.append(it.string.title())
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  el = article.find('meta', attrs={"itemprop": "image"})
  if el:
    item['_image'] = el['content']

  el = article.find('meta', attrs={"itemprop": "description"})
  if el:
    item['summary'] = el['content']

  story = article.find(class_='story-content-container')
  if story:
    for el in story.find_all(class_='container'):
      el.div.unwrap()
      el.unwrap()
  else:
    story = article

  for el in story.find_all(class_=['bottom-series-navigation', 'related-container', 'share-in-article-container', 'signoff']):
    el.decompose()

  for el in story.find_all(class_='article-subhead'):
    el.name = 'h3'

  for el in story.find_all('section'):
    if 'hide-title' in el['class']:
      it = el.find(class_=re.compile(r'title'))
      if it:
        it.decompose()
    if 'hide-byline' in el['class'] or 'hide-yline' in el['class']:
      it = el.find(class_=re.compile(r'byline'))
      if it:
        it.decompose()
    it = el.find(class_='article-row')
    if it:
      it.unwrap()
    el.insert_before(soup.new_tag('hr'))
    el.insert_after(soup.new_tag('hr'))
    el.unwrap()

  for el in story.find_all(class_='styled-box'):
    el.unwrap()

  for el in story.find_all(class_='carousel'):
    new_html = ''
    for it in el.find_all(class_='carousel-item'):
      images = []
      for src in it.picture.find_all('source'):
        image = {}
        image['src'] = src['srcset']
        m = re.search(r'max-width: (\d+)px', src['media'])
        if m:
          image['width'] = int(m.group(1))
          images.append(image)
      image = utils.closest_dict(images, 'width', 1000)
      caption = it.find(class_='caption')
      new_html += utils.add_image(image['src'], caption.get_text())
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in story.find_all('figure', class_='image'):
    new_html = ''
    if el.picture:
      images = []
      for it in el.picture.find_all('source'):
        image = {}
        image['src'] = it['srcset']
        m = re.search(r'max-width: (\d+)px', it['media'])
        if m:
          image['width'] = int(m.group(1))
          images.append(image)
      if images:
        image = utils.closest_dict(images, 'width', 1000)
        new_html = utils.add_image(image['src'], el.figcaption.get_text())
    elif el.img:
      new_html = utils.add_image(el.img['src'], el.figcaption.get_text())
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in story.find_all('figure', class_='video'):
    new_html = ''
    if el.video:
      new_html = utils.add_video(el.video.source['src'], el.video.source['type'], el.video['poster'], el.figcaption.get_text())
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in story.find_all('blockquote'):
    new_html = ''
    quote = el.find(class_='quote')
    credit = el.find(class_='credit')
    if quote and credit:
      new_html = utils.add_pullquote(quote.get_text(), credit.get_text())
    elif quote:
      new_html = utils.add_pullquote(quote.get_text())
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in story.find_all(class_='interactive'):
    src = ''
    if el.get('id'):
      if 'youtube-' in el['id']:
        # '#youtube-video-siddiqui').html('<iframe width="635" height="357" src="https://www.youtube.com/embed/T1KEA_Ab0Bg"
        m = re.search(r'\'#{}\'\)\.html\(\'<iframe.*src="([^"]+)"'.format(el['id']), article_content)
        if m:
          src = m.group(1)
      else:
        m = re.search(r'\'{}\', \'([^\']+)\''.format(el['id']), article_content)
        if m:
          src = m.group(1)
          if src.startswith('//'):
            src = 'https:' + src
    elif el.iframe and el.iframe.has_attr('src'):
      src = el.iframe['src']
    if src:
      new_html = utils.add_embed(src)
      if el.next_sibling.has_attr('class') and 'caption' in el.next_sibling['class']:
        if new_html.endswith('</blockquote>'):
          new_html = new_html[:-13] + '<br/><small>{}</small>'.format(utils.bs_get_inner_html(el.next_sibling))
          el.next_sibling.decompose()
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  def sub_has_dropcap(matchobj):
    return '{}<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(matchobj.group(1), matchobj.group(2), matchobj.group(3))
  for el in story.find_all(class_='dropcap'):
    new_html = re.sub(r'^(<[^>]+>)(\w)(.*)', sub_has_dropcap, str(el))
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in story.find_all(class_='storyparts'):
    el.contents[0].wrap(soup.new_tag('i'))

  item['content_html'] = ''
  el = soup.find(class_='masthead-container')
  if el:
    it = soup.find(class_='masthead-image')
    if it:
      # background-image:url('https://www.reuters.com/investigates/special-report/assets/usa-oneamerica-att/mastheads/oan-att-lead.jpg?v=232322061021');
      m = re.search(r'background-image:url\(\'([^\']+)\'\)', it['style'])
      if m:
        item['content_html'] = utils.add_image(m.group(1))
    else:
      it = soup.find('video')
      if it:
        item['content_html'] = utils.add_video(it.source['src'], it.source['type'], it['poster'])

  el = article.find(class_='dek', attrs={"itemprop":"description"})
  if el:
    item['content_html'] += '<p>{}</p><hr width="80%"/>'.format(utils.bs_get_inner_html(el))

  item['content_html'] += utils.bs_get_inner_html(story)
  return item

def get_item(content, url, args, save_debug):
  item = {}
  item['id'] = content['id']
  item['url'] = 'https://www.reuters.com' + content['canonical_url']
  item['title'] = content['title']

  dt = datetime.fromisoformat(content['published_time'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(content['updated_time'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  authors = []
  for byline in content['authors']:
    authors.append(byline['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = content['taxonomy']['keywords'].copy()

  lead_image = None
  if content['promo_items'].get('images'):
    lead_image = content['promo_items']['images'][0]
    item['_image'] = resize_image(content['promo_items']['images'][0], 480)

  item['summary'] = content['description']

  item['content_html'] = fusion.get_content_html(content, lead_image, resize_image, url, save_debug)
  return item

def get_content(url, args, save_debug=False, d=''):
  if '/investigates/' in url:
    return get_investigates_content(url, args, save_debug)

  split_url = urlsplit(url)
  if not d:
    d = fusion.get_domain_value('{}://{}'.format(split_url.scheme, split_url.netloc))
    if not d:
      return None

  query = '{{"uri":"{0}", "website":"reuters", "published":"true", "website_url":"{0}","arc-site":"reuters"}}'.format(split_url.path)
  api_url = 'https://www.reuters.com/pf/api/v3/content/fetch/article-by-id-or-url-v1?query={}&d={}&_website=reuters'.format(quote_plus(query), d)

  if save_debug:
    logger.debug('getting content from ' + api_url)
  url_json = utils.get_url_json(api_url)
  if not (url_json and url_json.get('result')):
    return None

  content = url_json['result']
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(content, file, indent=4)

  return get_item(content, url, args, save_debug)

def get_investigates_feed(args, save_debug=False):
  content = utils.get_url_content(args['url'])
  if not content:
    return None

  page_content = content.decode('utf-8')
  soup = BeautifulSoup(page_content, 'html.parser')

  n = 0
  items = []
  for article in soup.find_all('article'):
    item = get_investigates_content(article.a['href'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed

def get_feed(args, save_debug=False):
  if '/investigates/' in args['url']:
    return get_investigates_feed(args, save_debug)

  split_url = urlsplit(args['url'])
  d = fusion.get_domain_value('{}://{}'.format(split_url.scheme, split_url.netloc))
  if not d:
    return None

  section = split_url.path
  if section.endswith('/'):
    section = section[:-1]
  #query = '{{"fetch_type":"section","id":"{}","orderby":"last_updated_date:desc","size":10,"website":"reuters"}}'.format(section)
  query = '{{"uri":"/{0}/","website":"reuters","id":"{0}","fetch_type":"collection","orderby":"last_updated_date:desc","size":"20","section_id":"{0}","arc-site":"reuters"}}'.format(section)
  api_url = 'https://www.reuters.com/pf/api/v3/content/fetch/articles-by-section-alias-or-id-v1?query={}&d={}&_website=reuters'.format(quote_plus(query), d)
  section_json = utils.get_url_json(api_url)
  if not section_json:
    return None
  if save_debug:
    with open('./debug/feed.json', 'w') as file:
      json.dump(section_json, file, indent=4)
  
  n = 0
  items = []
  for article in section_json['result']['articles']:
    url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['canonical_url'])

    # Check age (make a fake item with the timestamp)
    item = {}
    dt_pub = datetime.fromisoformat(article['published_time'].replace('Z', '+00:00'))
    item['_timestamp'] = dt_pub.timestamp()
    if args.get('age'):
      if not utils.check_age(item, args):
        if save_debug:
          logger.debug('skipping old article ' + url)
        continue

    item = get_content(url, args, save_debug, d)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed