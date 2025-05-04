from flask import Flask, render_template, jsonify, request
import json
import random
from collections import defaultdict

app = Flask(__name__)

# Load flashcards data
with open('flashcards.json', 'r') as file:
    FLASHCARDS = json.load(file)

# Create indices for quick filtering
MODULE_INDEX = defaultdict(list)
TOPIC_INDEX = defaultdict(list)
SUBTOPIC_INDEX = defaultdict(list)
TAG_INDEX = defaultdict(list)

# Build indices
for idx, card in enumerate(FLASHCARDS):
    MODULE_INDEX[card['Module']].append(idx)
    TOPIC_INDEX[card['Topic']].append(idx)
    SUBTOPIC_INDEX[card['Sub-Topic']].append(idx)
    for tag in card['Tags']:
        TAG_INDEX[tag].append(idx)

def get_unique_values(key):
    return sorted(list(set(card[key] for card in FLASHCARDS)))

def get_similar_answers(correct_card, count=3):
    similar_answers = []
    module_cards = [FLASHCARDS[idx] for idx in MODULE_INDEX[correct_card['Module']]]
    
    # Try matching by tags first
    tag_matches = []
    for card in module_cards:
        if card != correct_card:
            common_tags = set(card['Tags']) & set(correct_card['Tags'])
            if common_tags:
                tag_matches.append((len(common_tags), card))
    
    # Try matching by sub-topic if we need more
    if len(tag_matches) < count:
        subtopic_matches = [
            card for card in module_cards
            if card != correct_card 
            and card['Sub-Topic'] == correct_card['Sub-Topic']
            and card not in [m[1] for m in tag_matches]
        ]
        tag_matches.extend((0, card) for card in subtopic_matches)
    
    # Try matching by topic if we still need more
    if len(tag_matches) < count:
        topic_matches = [
            card for card in module_cards
            if card != correct_card 
            and card['Topic'] == correct_card['Topic']
            and card not in [m[1] for m in tag_matches]
            and card not in subtopic_matches
        ]
        tag_matches.extend((0, card) for card in topic_matches)
    
    # Sort by number of matching tags and select top matches
    tag_matches.sort(key=lambda x: x[0], reverse=True)
    similar_answers = [m[1]['Answer'] for m in tag_matches[:count]]
    
    # If we still need more, add random answers from the same module
    while len(similar_answers) < count:
        random_card = random.choice(module_cards)
        if random_card['Answer'] not in similar_answers and random_card != correct_card:
            similar_answers.append(random_card['Answer'])
    
    return similar_answers

@app.route('/')
def index():
    return render_template('index.html',
                         modules=get_unique_values('Module'),
                         topics=get_unique_values('Topic'),
                         subtopics=get_unique_values('Sub-Topic'))

@app.route('/get_filters', methods=['POST'])
def get_filters():
    selected_module = request.json.get('module')
    selected_topic = request.json.get('topic')
    selected_subtopic = request.json.get('subtopic')
    
    filtered_cards = FLASHCARDS
    
    if selected_module:
        filtered_cards = [card for card in filtered_cards if card['Module'] == selected_module]
    if selected_topic:
        filtered_cards = [card for card in filtered_cards if card['Topic'] == selected_topic]
    if selected_subtopic:
        filtered_cards = [card for card in filtered_cards if card['Sub-Topic'] == selected_subtopic]
    
    return jsonify({
        'topics': sorted(list(set(card['Topic'] for card in filtered_cards))),
        'subtopics': sorted(list(set(card['Sub-Topic'] for card in filtered_cards)))
    })

@app.route('/get_question', methods=['POST'])
def get_question():
    selected_module = request.json.get('module')
    selected_topic = request.json.get('topic')
    selected_subtopic = request.json.get('subtopic')
    selected_tags = request.json.get('tags', [])
    
    # Filter cards based on selections
    filtered_cards = FLASHCARDS
    if selected_module:
        filtered_cards = [card for card in filtered_cards if card['Module'] == selected_module]
    if selected_topic:
        filtered_cards = [card for card in filtered_cards if card['Topic'] == selected_topic]
    if selected_subtopic:
        filtered_cards = [card for card in filtered_cards if card['Sub-Topic'] == selected_subtopic]
    if selected_tags:
        filtered_cards = [
            card for card in filtered_cards 
            if any(tag in card['Tags'] for tag in selected_tags)
        ]
    
    if not filtered_cards:
        return jsonify({'error': 'No cards match the selected filters'})
    
    # Select random card
    question_card = random.choice(filtered_cards)
    
    # Get similar answers
    wrong_answers = get_similar_answers(question_card)
    
    # Combine and shuffle answers
    all_answers = wrong_answers + [question_card['Answer']]
    random.shuffle(all_answers)
    
    return jsonify({
        'question': question_card['Question'],
        'correct_answer': question_card['Answer'],
        'answers': all_answers,
        'module': question_card['Module'],
        'topic': question_card['Topic'],
        'subtopic': question_card['Sub-Topic'],
        'tags': question_card['Tags']
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0",debug=True, port=2456)
