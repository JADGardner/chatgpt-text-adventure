import sys
import requests
import threading
import queue
import json
import random

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import pyqtSignal
from openai import OpenAI

from gui import GUI, IntroDialog, get_path

class Game:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.api_key = None
        self.text_queue = queue.Queue()
        self.image_queue = queue.Queue()
        self.stream_lock = threading.Lock()
        self.image_lock = threading.Lock()
        self.button_pressed_lock = threading.Lock()
        self.game_loop_thread = threading.Thread(target=self.game_loop)
        self.button_pressed = None
        self.terminate_threads = False
        self.terminate_threads_lock = threading.Lock()
        self.game_state = 'initialising'
        self.retry_limit = 3  # Set a reasonable retry limit for the DALL-E API

    def run(self):
        intro_dialog = IntroDialog()
        if intro_dialog.exec_() == QDialog.Accepted:
            self.api_key = intro_dialog.api_key
            self.gui = GUI(parent=self, width=300, height=800, title="Pete's Last Day")
            self.gui.button_clicked_signal.connect(self.handle_button_click)
            self.gui.close_signal.connect(self.handle_close)
            # TODO make sure they have entered a key
            self.client = OpenAI(api_key=self.api_key)
            self._intialise_game()
            # Start the game loop
            self.game_state = 'llm_streaming'
            self.start_stream_thread(self.messages)
            self.game_loop_thread.start()
            sys.exit(self.app.exec_())
    
    def handle_close(self):
        with self.terminate_threads_lock:
            self.terminate_threads = True
        
        self.game_loop_thread.join()
        sys.exit()

    def fetch_stream(self, messages):
        with self.stream_lock:
            stream = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                stream=True,
            )
            for chunk in stream: # pylint: disable=E1133
                if chunk.choices[0].finish_reason is not None:
                    # Response has finished
                    self.text_queue.put((chunk.choices[0].delta.content or "", True))
                    break
                else:
                    # Still receiving response
                    self.text_queue.put((chunk.choices[0].delta.content or "", False))

    def generate_image(self, text):
        retry_count = 0

        while retry_count < self.retry_limit:
            try:
                # Generate a new prompt
                latest_prompt_addition, img_prompt = self._generate_prompt(text)

                # Attempt to generate an image
                response = self.client.images.generate(
                    model="dall-e-3",
                    prompt=img_prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                url = response.data[0].url

                # Process and update the image
                pixmap = self._load_image(url)
                self.gui.update_image_signal.emit(pixmap)
                break  # Exit loop if successful
            
            except Exception as _:
                retry_count += 1
                if retry_count >= self.retry_limit:
                    raise  # Re-raise the exception if retry limit is reached
        
        self.dalle_prompts.append(latest_prompt_addition)

    def _load_image(self, url):
        # Load image from URL and return QPixmap
        response = requests.get(url, stream=True)
        response.raise_for_status()
        pixmap = QPixmap()
        pixmap.loadFromData(response.content)
        return pixmap

    def generate_image(self, text):
        prompt = text

        with self.image_lock:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            url = response.data[0].url
            # use request to stream image into a QPixmap and emit signal to update image
            # Download the image from the URL
            response = requests.get(url, stream=True)
            response.raise_for_status()  # This will raise an exception for HTTP errors

            # Convert the response content into a QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)

            # Emit the signal to update the image
            self.gui.update_image_signal.emit(pixmap)
            

    def start_stream_thread(self, messages):
        stream_thread = threading.Thread(target=self.fetch_stream, args=(messages,))
        stream_thread.start()

    def start_image_thread(self, prompt):
        image_thread = threading.Thread(target=self.generate_image, args=(prompt,))
        image_thread.start()

    def find_action(self, text):
      # Check if the text contains an action
      # Actions are preappended in a spectial emoji 🥒
      return "🥒" in text
    
    def find_win(self, text):
      return "🏁" in text
    
    def find_death(self, text):
      return "💀" in text
    
    def find_image_prompt(self, text):
        return "📷" in text
    
    def handle_button_click(self, button_index):
      with self.button_pressed_lock:
          if self.game_state == 'waiting_for_user_input':
              self.button_pressed = button_index
          else:
              self.button_pressed = None

    def _intialise_game(self):
        self.turn = 1
        self.moral_tally = {
            "good": 0,
            "neutral": 0,
            "evil": 0
        }
        self.random_event = None

        # load the game config
        # TODO Make this an dropdown in the opening GUI and set the title of the GUI to the game name
        config_path = get_path('pete_game_config.json')
        with open(config_path) as f:
            config = json.load(f)

        self.objective = random.choice(config['objectives'])
        self.theme = random.choice(config['themes'])
        self.writing_style = random.choice(config['writing_style'])
        self.random_events = config['random_events']
        self.image_gen_style = random.choice(config['image_gen_styles'])
        
        # intial prompt is a list of strings that need combining
        initial_prompt = "".join(config['initial_prompt'])
        # change 'OBJECTIVE' in initial_prompt to a random objective capitalisation is important
        initial_prompt = initial_prompt.replace('OBJECTIVE', self.objective)
        # same again for STYLE, choose a writing style
        initial_prompt = initial_prompt.replace('STYLE', self.writing_style)
        # same again for THEME, choose a theme
        initial_prompt = initial_prompt.replace('THEME', self.theme)
        # and update FAIL_STATES with the fail states
        fail_states = ", ".join(config['fail_states'])
        initial_prompt = initial_prompt.replace('FAIL_STATES', fail_states)

        self.messages = [
          {"role": "system", "content": "You are a helpful assistant and master storyteller, you craft stories that are engaging and deeply meaningful."},
          {"role": "user", "content": initial_prompt}
        ]
        self.dalle_prompts = [
          {"role": "system", "content": "You are a helpful assistant."},
        ]
    
    def game_loop(self):
        action_count = -1
        reading_actions = False
        reading_image_prompt = False
        cameras_detected = 0
        self.button_pressed = None
        gpt_response_full = ""
        win = False
        death = False
        game_running = True
        downloading_image = False
        current_paragraph = ""
        image_prompt = ""
        while game_running:
            with self.terminate_threads_lock:
                if self.terminate_threads:
                    game_running = False
                    continue
            if self.game_state == 'llm_streaming':
                try:
                    text, finished = self.text_queue.get(timeout=1)
                    if self.find_action(text):
                        # TODO Don't show alginment of actions in the GUI
                        # TODO randomise the actions so they are not always in the same order
                        reading_actions = True
                        action_count += 1
                    if self.find_image_prompt(text):
                        reading_image_prompt = True
                        cameras_detected += 1
                    if self.find_win(text):
                        # remove the win flag from the text
                        text = text.replace("🏁", "")
                        win = True # TODO do something with this
                    if self.find_death(text):
                        # remove the death flag from the text
                        text = text.replace("💀", "")
                        death = True # TODO do something with this
                    if reading_actions:
                        self.gui.update_button_single_signal.emit(action_count, text, False) # Emit signal with text, False means append not overwrite
                    elif reading_image_prompt:
                        image_prompt += text
                        if cameras_detected == 2:
                            reading_image_prompt = False
                    else:
                        self.gui.update_text_signal.emit(text, False)  # Emit signal with text, False means append not overwrite
                        current_paragraph += text
                    gpt_response_full += text
                    if finished:
                        self.game_state = 'waiting_for_user_input'
                except queue.Empty:
                    continue
                with self.button_pressed_lock:
                    if self.button_pressed is not None:
                        self.button_pressed = None

            elif self.game_state == 'waiting_for_user_input':
                if not downloading_image:
                    self.start_image_thread(image_prompt)
                    downloading_image = True
                with self.button_pressed_lock:
                    current_button_pressed = self.button_pressed
                    if current_button_pressed is None:
                            continue
                    else:
                        self.turn += 1
                        finished = False
                        # convert button press to moral choice to update tally
                        if current_button_pressed == 0:
                            self.moral_tally["good"] += 1
                        elif current_button_pressed == 1:
                            self.moral_tally["neutral"] += 1
                        elif current_button_pressed == 2:
                            self.moral_tally["evil"] += 1

                        user_reponse = f"ACTION SELCTED: {current_button_pressed + 1}\n\nTurn: {self.turn}/5, Tally: G-{self.moral_tally['good']}, N-{self.moral_tally['neutral']}, E-{self.moral_tally['evil']}, "

                        # choose a random event or not with 30% chance
                        if random.random() < 0.3:
                            random_event = random.choice(self.random_events)
                            user_reponse += f"Random Event: {random_event}"
                        else:
                            user_reponse += "Random Event: None"

                        self.messages.append({"role": "assistant", "content": gpt_response_full})
                        self.messages.append({"role": "user", "content": user_reponse})

                        # save messages to text file
                        with open('messages.txt', 'w') as f:
                            for message in self.messages:
                                # just write the content
                                f.write(message['content'] + '\n')

                        self.game_state = 'llm_streaming'
                        for i in range(3):
                            self.gui.update_button_single_signal.emit(i, "", True)
                        self.gui.update_text_signal.emit("", True)
                        action_count = -1
                        reading_actions = False
                        reading_image_prompt = False
                        cameras_detected = 0
                        downloading_image = False
                        current_paragraph = ""
                        self.button_pressed = None
                        self.start_stream_thread(self.messages)

if __name__ == "__main__":
    game = Game()
    game.run()