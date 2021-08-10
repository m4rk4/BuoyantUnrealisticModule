import json
from bs4 import BeautifulSoup
from datetime import datetime

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  if url.endswith('/'):
    json_url = url[:-1] + '.json'
  else:
    json_url = url + '.json'
  article_json = utils.get_url_json(json_url)
  if not article_json:
    return get_content_from_html(url, args, save_debug)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(article_json, file, indent=4)

  item = {}

  if '/video/' in url:
    item['id'] = article_json['_id'] 
    item['url'] = url
    item['title'] = article_json['title']
    item['_image'] = article_json['image']
    
    vid_src = '"https://vdist.aws.mashable.com/' + article_json['source']
    item['content_html'] = utils.add_video(vid_src, 'video/mp4', article_json['image'])

    article_html = utils.get_url_html(url)
    if article_html:
      soup = BeautifulSoup(article_html, 'html.parser')

      el = soup.find('meta', attrs={"property": "og:article:published_time"})
      if el:
        dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

      el = soup.find('meta', attrs={"property": "og:article:modified_time"})
      if el:
        dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

      el = soup.find('meta', attrs={"name": "author"})
      if el:
        item['author'] = {}
        item['author']['name'] = el['content']

      el = soup.find(class_='video-description')
      if el:
        item['content_html'] += str(el)
  else:
    item['id'] = article_json['post']['_id'] 
    item['url'] = url
    item['title'] = article_json['post']['title']

    dt_pub = datetime.fromisoformat(article_json['post']['post_date'])
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = article_json['post']['author']

    item['_image'] = article_json['post']['image']
    item['summary'] = article_json['post']['excerpt']

    # add lead image
    content_html = utils.add_image(article_json['post']['image'])

    if article_json['post'].get('shortcode_data') and article_json['post']['shortcode_data'].get('productreview'):
      try:
        review_data = article_json['post']['shortcode_data']['productreview'][0]
        content_html += '<table style="border: 1px solid black;"><tr><td colspan="2"><center><b>{}</b><br />${}</center></td></tr>'.format(review_data['data-product-name'], review_data['data-product-price'])
        content_html += '<tr><td width="50%" style="vertical-align:top;"><u>The Good:</u><ul>'
        for it in review_data['data-product-good'].split(','):
          content_html += '<li>{}</li>'.format(it)
        content_html += '</ul>'
        content_html += '<u>The Bad:</u><ul>'
        for it in review_data['data-product-bad'].split(','):
          content_html += '<li>{}</li>'.format(it)
        content_html += '</ul></td>'
        content_html += '<td width="50%" style="vertical-align:top;"><u>{} - {}</u><ul style="list-style-type:none;"><li>{} - {}</li><li>{} - {}</li><li>{} - {}</li><li>{} - {}</li></ul>'.format(review_data['data-product-score-title'], review_data['data-product-score'], review_data['data-product-coolness-title'], review_data['data-product-coolness'], review_data['data-product-curve-title'], review_data['data-product-curve'], review_data['data-product-performance-title'], review_data['data-product-performance'], review_data['data-product-bang-for-the-buck-title'], review_data['data-product-value'])
        content_html += '<u>The Bottoml Line:</u><ul style="list-style-type:none;"><li>{}</li></ul></td></tr></table>'.format(review_data['data-product-blurb'])
      except:
        logger.warning('error with the product review data in ' + url)
        content_html = ''

    soup = BeautifulSoup(article_json['post']['content']['full'], 'html.parser')
    for el in soup.find_all('figure', class_='image'):
      img = el.find('img')
      img_caption = el.find(class_='image-credit')
      if img_caption:
        new_img = utils.add_image(img['src'], utils.bs_get_inner_html(img_caption.p))
      else:
        new_img = utils.add_image(img['src'])
      new_el = BeautifulSoup(new_img, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

    for el in soup.find_all(class_='content-mash-video'):
      data = el.find('script', class_='playerMetadata')
      if data:
        data_json = json.loads(str(data.contents[0]))
        vid_src = ''
        vid_type = ''
        # look for mp4 sources
        for src in data_json['player']['sources']:
          if '.mp4' in src['file']:
            vid_src = src['file']
          if '480.mp4' in src['file']:
            vid_src = src['file']
            vid_type = 'video/mp4'
        # if no mp4, use m3u8 playlist
        if not vid_src:
          for src in data_json['player']['sources']:
            if '.m3u8' in src['file']:
              vid_src = src['file']
              vid_type = 'application/x-mpegURL'
        if vid_src:
          new_el = BeautifulSoup(utils.add_video(vid_src, vid_type, data_json['player']['image']), 'html.parser')
          el.insert_after(new_el)
          el.decompose()
        else:
          logger.warning('unknown video source in ' + url)
      else:
        logger.warning('no mash-video data in ' + url)

    for el in soup.find_all(class_='youtube-wrapper'):
      data = el.find('iframe')
      if data:
        new_el = BeautifulSoup(utils.add_youtube(str(data)), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
      else:
        logger.warning()

    #for el in soup.find_all(class_='twitter-wrapper'):

    for el in soup.find_all('blockquote', class_="pull-quotes"):
      new_el = BeautifulSoup(utils.add_blockquote(utils.bs_get_inner_html(el.p)), 'html.parser')
      el.insert_after(new_el)
      el.decompose()

    for el in soup.find_all('script'):
      el.decompose()

    item['content_html'] = content_html + str(soup)
  return item
  
def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  for feed_item in feed['items']:
    item = get_content(feed_item['url'], args, save_debug)
    if feed_item.get('tags'):
      item['tags'] = feed_item['tags'].copy()
    if utils.filter_item(item, args) == True:
      items.append(item)
      n += 1
      if 'max' in args:
        if n == int(args['max']):
          break
  feed['items'] = items.copy()
  return feed