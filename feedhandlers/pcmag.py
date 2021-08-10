import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import utils
from feedhandlers import twitter

import logging
logger = logging.getLogger(__name__)

def resize_image(img_path):
  #h = math.ceil(int(height)*int(w)/int(width))
  path, fmt = img_path.split('.')
  return 'https://i.pcmag.com/imagery/{}.fit_lim.size_640x.{}'.format(path, fmt)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  soup = BeautifulSoup(article_html, 'html.parser')
  article_page = soup.find(attrs={"tracking-source": "article-page"})
  if not article_page:
    article_page = soup.find(attrs={"tracking-source": "review-page"})
  if not article_page:
    logger.warning('unable to extract article json from ' + url)
    return None

  def replace_quot(matchobj):
    return matchobj.group(0).replace('&quot;', '"')
  article_data = re.sub(r'({|,|:)&quot;\w|\w&quot;(}|,|:)', replace_quot, article_page['context'])
  if save_debug:
    with open('./debug/debug.txt', 'w', encoding='utf-8') as f:
      f.write(article_data)

  article_json = json.loads(article_data)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(article_json, file, indent=4)
  
  item = {}
  item['id'] = article_json['id']
  item['url'] = url
  item['title'] = article_json['title']

  dt = datetime.fromisoformat(article_json['published_at'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_json['updated_at'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  authors = []
  for author in article_json['authors']:
    authors.append('{} {}'.format(author['first_name'], author['last_name']))
  item['author'] = {}
  item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = []
  for cat in article_json['categories']:
    item['tags'].append(cat['name'])

  item['_image'] = resize_image(article_json['images']['images'][0]['path'])
  item['summary'] = article_json['deck']

  item['content_html'] = ''

  def get_block_content(block, i):
    nonlocal url
    block_html = ''
    if block['type'] == 'text':
      if block.get('marks'):
        end_tag = ''
        for mark in block['marks']:
          if mark['type'] == 'link':
            block_html += '<a href="{}">'.format(mark['attrs']['href'])
            end_tag = '</a>' + end_tag
          elif mark['type'] == 'italic':
            block_html += '<i>'
            end_tag = '</i>' + end_tag
          elif mark['type'] == 'bold':
            block_html += '<b>'
            end_tag = '</b>' + end_tag
        block_html += block['text'] + end_tag
      else:
        block_html += block['text']

    elif block['type'] == 'paragraph':
      block_html += '<p>'
      if block.get('content'):
        for content in block['content']:
          block_html += get_block_content(content, i)
      block_html += '</p>'

    elif block['type'] == 'code_block':
      # If it's the first block, it's likely the lead image caption so skip it
      if i > 0:
        block_html += '<p>'
        for content in block['content']:
          block_html += get_block_content(content, i)
        block_html += '</p>'
    
    elif block['type'] == 'heading':
      block_html += '<h{}>'.format(block['attrs']['level'])
      for content in block['content']:
        block_html += get_block_content(content, i)
      block_html += '</h{}>'.format(block['attrs']['level'])

    elif block['type'] == 'horizontal_rule':
      block_html += '<hr width="80%" />'

    elif block['type'] == 'bullet_list':
      block_html += '<ul>'
      for list_item in block['content']:
        block_html += get_block_content(list_item, i)
      block_html += '</ul>'

    elif block['type'] == 'ordered_list':
      block_html += '<ol>'
      for list_item in block['content']:
        block_html += get_block_content(list_item, i)
      block_html += '</ol>'

    elif block['type'] == 'list_item':
      block_html += '<li>'
      for content in block['content']:
        block_html += get_block_content(content, i)
      block_html += '</li>'

    elif block['type'] == 'eloquent_imagery_image':
      block_html += utils.add_image(resize_image(block['attrs']['path']), block['attrs']['caption'])

    elif block['type'] == 'youtube_video':
      block_html += utils.add_youtube(block['attrs']['id'])

    elif block['type'] == 'mashable_video':
      m = re.search('({{"slug":"{}"[^}}]+}})'.format(block['attrs']['id']), article_html)
      if m:
        video_json = json.loads(m.group(1))
        if video_json:
          video_src = ''
          for fmt in ['480.mp4', '720.mp4', '1080.mp4']:
            for src in video_json['transcoded_urls']:
              if src.endswith(fmt):
                video_src = src
                break
            if video_src:
              break
          if not video_src:
            video_src = video_json['url']
          block_html += utils.add_video(video_src, 'video/mp4', video_json['thumbnail_url'], video_json['title'])

    elif block['type'] == 'twitter_embed':
      tweet = twitter.get_content('https://twitter.com/' + block['attrs']['id'], None)
      block_html += tweet['content_html']

    elif block['type'] == 'infogram_embed':
      infogram_json = utils.get_url_json('https://infogram.com/oembed/?url=' + quote_plus(block['attrs']['url']))
      if infogram_json:
        block_html += utils.add_image(infogram_json['thumbnail_url'], '<a href="{}">{}</a>'.format(infogram_json['uri'], infogram_json['title']))
      else:
        block_html += '<p><a href="">Infogram embed chart</a>'.format(block['attrs']['url'])

    elif block['type'] == 'hard_break':
      pass

    else:
      logger.warning('unhandled content block type {} in {}'.format(block['type'], url)) 
    return block_html

  # Lead image
  caption = ''
  if article_json['body_content_blocks']['content'][0]['type'] == 'code_block':
    for content in article_json['body_content_blocks']['content'][0]['content']:
      caption += get_block_content(content, 1)
    caption = BeautifulSoup(caption, 'html.parser').get_text()
  else:
    caption = ''
  item['content_html'] += utils.add_image(item['_image'], caption)

  # Review summary
  if article_json.get('is_editors_choice') and article_json['is_editors_choice']== True:
    item['content_html'] += '<center><img height="60px" src="https://www.pcmag.com/images/editors-choice-horizontal.png" /></center>'
  if article_json.get('score'):
    item['content_html'] += '<center><h2>Review score: {}</h2></center>'.format(article_json['score'])
  if article_json.get('bottom_line'):
    item['content_html'] += '<h2>Bottom Line</h2><p>{}</p>'.format(article_json['bottom_line'])
  if article_json.get('pros'):
    item['content_html'] += '<h2>Pros:</h2><ul>'
    for it in article_json['pros'].split('\n'):
      item['content_html'] += '<li>{}</li>'.format(it)
    item['content_html'] += '</ul>'
  if article_json.get('cons'):
    item['content_html'] += '<h2>Cons</h2><ul>'
    for it in article_json['cons'].split('\n'):
      item['content_html'] += '<li>{}</li>'.format(it)
    item['content_html'] += '</ul><hr width="80%" />'

  # Article body
  #item['content_html'] += article_json['body']
  for i, block in enumerate(article_json['body_content_blocks']['content']):
    item['content_html'] += get_block_content(block, i)
  
  return item

def get_feed(args, save_debug=False):
  page_html = utils.get_url_html(args['url'])
  if not page_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(page_html)

  soup = BeautifulSoup(page_html, 'html.parser')

  n = 0
  items = []
  feed = utils.init_jsonfeed(args)
  if '/reviews' in args['url']:
    links = soup.find_all('a', attrs={"data-element":"review-title"})
  else:
    links = soup.find_all('a', attrs={"data-element":"article-title"})
  for a in links:
    url = a['href']
    if not url.startswith('https://www.pcmag.com/'):
      url = 'https://www.pcmag.com' + a['href']
    if save_debug:
      logger.debug('getting content from ' + url)
    item = get_content(url, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed
