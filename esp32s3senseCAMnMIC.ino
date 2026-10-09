#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESP_I2S.h>

const char* ssid = "Astrid Sin Iphone";
const char* password = "Astrid0909";

#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15

#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

const int FPS = 20;
const unsigned long FRAME_INT = 1000/FPS;

const int MIC_CLK = 42;
const int MIC_DATA = 41;

I2SClass microphone;

WebServer server(80);
WebServer audioServer(81);
WebServer temperatureServer(82);

//---------------------------------------------------------
//CAMERA PART
// https://github.com/arkhipenko/esp32-mjpeg-multiclient-espcam-drivers/blob/master/Arduino-IDE/esp32-cam/esp32-cam.ino

void handleStream() {
  WiFiClient client = server.client();
  client.setNoDelay(true);

  //talks to the web server about the status and content of the input
  client.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    "Cache-Control: no-cache\r\n"
    "Pragma: no-cache\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "\r\n"
  );

  while (client.connected()) {
    unsigned long frameStart = millis();
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      delay(10);
      continue;
    }

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: ");
    client.print(fb->len);
    client.print("\r\n\r\n");

    // Send HELE JPEG-bildet, selv dersom TCP bare
    // godtar deler av bufferen av gangen.
    size_t totalSent = 0;

    while (totalSent < fb->len && client.connected()) {
      size_t sent = client.write(fb->buf + totalSent, fb->len - totalSent);

      if (sent == 0) {
        delay(1);
        continue;
      }

      totalSent += sent;
    }

    client.print("\r\n");
    esp_camera_fb_return(fb);
    if (!client.connected()) {
      break;
    }

    unsigned long frameTime = millis() - frameStart;

    if (frameTime < FRAME_INT){
      delay(FRAME_INT - frameTime);
    }
  }

  client.stop();

  Serial.println("Stream disconnected");
}


//-----------------------------------------------
//AUDIO PART

//https://esp32.com/viewtopic.php?t=16775 
typedef struct __attribute__((packed)) {
  uint32_t chunk_id;
  uint32_t chunk_size;
  uint32_t format;
} chunk_riff_t;

typedef struct __attribute__((packed)) {
  uint32_t chunk_id;
  uint32_t chunk_size;
  uint16_t audio_format;
  uint16_t num_of_channels;
  uint32_t samplerate;
  uint32_t byterate;
  uint16_t block_align;
  uint16_t bits_per_sample;
} chunk_fmt_t;

typedef struct __attribute__((packed)) {
  uint32_t chunk_id;
  uint32_t chunk_size;
} chunk_data_t;

typedef struct __attribute__((packed)) {
  chunk_riff_t riff;
  chunk_fmt_t fmt;
  chunk_data_t data;
} wav_header_t;

void wavHeader(wav_header_t* wav,int sampleRate,int channels,int bitsPerSample,int dataSize);

void wavHeader(wav_header_t* wav,int sampleRate,int channels,int bitsPerSample,int dataSize) {
  wav->riff.chunk_id = 0X46464952;
  wav->riff.chunk_size = dataSize + 36;
  wav->riff.format = 0X45564157;
  wav->fmt.chunk_id = 0X20746D66;
  wav->fmt.chunk_size = 16;
  wav->fmt.audio_format = 1;
  wav->fmt.num_of_channels = channels;
  wav->fmt.samplerate = sampleRate;
  wav->fmt.byterate = sampleRate * channels * bitsPerSample / 8;
  wav->fmt.block_align = channels * bitsPerSample / 8;
  wav->fmt.bits_per_sample = bitsPerSample;
  wav->data.chunk_id = 0X61746164;
  wav->data.chunk_size = dataSize;
}

void handleAudio() {
  WiFiClient client = audioServer.client();

  const int sampleRate = 16000;
  const int channels = 1;
  const int bitsPerSample = 16;
  const int seconds = 4;
  const int dataSize = sampleRate * seconds * channels * bitsPerSample / 8;

  wav_header_t wav;
  wavHeader(&wav,sampleRate,channels,bitsPerSample,dataSize);

  client.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: audio/wav\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "Connection: close\r\n"
    "Content-Length: "
  );

  client.print(dataSize + sizeof(wav));
  client.print("\r\n\r\n");
  client.write((uint8_t*)&wav,sizeof(wav));

  uint8_t buffer[1024];
  int totalSent = 0;

  while (totalSent < dataSize && client.connected()) {
    int bytesToRead = min((int)sizeof(buffer),dataSize - totalSent);
    int bytesRead = microphone.readBytes((char*)buffer,bytesToRead);

    if (bytesRead > 0) {
      client.write(buffer,bytesRead);
      totalSent += bytesRead;
    }
  }

  client.stop();
}

void audioServerTask(void* parameter) {
  while (true) {
    audioServer.handleClient();
    delay(1);
  }
}



//-----------------------------------------------------
//TEMPERATURE SENSOR TO WEBPAGE
void handleTemperature(){
  float temperature = temperatureRead();

  String html =
    "<html>"
    "<head><meta http-equiv=\"refresh\" content=\"1\"></head>"
    "<body>"
    "<h1>ESP32-S3 internal temp</h1>"
    "<p>" + String(temperature,1) + " C</p>"
    "</body>"
    "</html>";

  temperatureServer.send(200,"text/html",html);
}

void temperatureServerTask(void* parameter){
  while(true) {
    temperatureServer.handleClient();
    delay(1);
  }
}

//-----------------------------------------------
//CAMERA SETUP

//https://www.electromaker.io/project/view/getting-started-with-xiao-esp32-s3-sense?srsltid=AU7gw4VJBEL_3PLCF3pPkriND8qC47JZaFUNncwbzz0_oTzDuYu4V9fi
//https://randomnerdtutorials.com/esp32-cam-video-streaming-web-server-camera-home-assistant/ 
void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println();
  Serial.println("Starting XIAO ESP32S3 camera...");


  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_SXGA;
  config.pixel_format = PIXFORMAT_JPEG; //for streaming
  

  //VIKTIG - vurder om vi skal gjøre det som står er best for facedetection/recognition

//config.pixel_format = PIXFORMAT_RGB565; //vurdere ? er for face detection/recognition
  //if(config.pixel_format == PIXFORMAT_JPEG){
    //if(psramFound()){
      //config.jpeg_quality = 10;
      //config.fb_count = 2;
      //config.grab_mode = CAMERA_GRAB_LATEST;
    //} else {
      // Limit the frame size when PSRAM is not available
      //config.frame_size = FRAMESIZE_SVGA;
      //config.fb_location = CAMERA_FB_IN_DRAM;
    //}
  //} else {
    // Best option for face detection/recognition
    //config.frame_size = FRAMESIZE_240X240;
//#if CONFIG_IDF_TARGET_ESP32S3
    //config.fb_count = 2;
//#endif
  //}

  config.jpeg_quality = 12;
  float temperature = temperatureRead();
  const char* framesize_chosen;


  if (psramFound()) {
    if (temperature > 65) {
      config.frame_size = FRAMESIZE_XGA;
      framesize_chosen = "XGA";
    } else {
      config.frame_size = FRAMESIZE_SXGA;
      framesize_chosen = "SXGA";
    }
    Serial.println(framesize_chosen);
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    config.frame_size = FRAMESIZE_SVGA; 
  }

  //camera initialization
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  Serial.println("Camera initialised.");

  // camera: OV3660
  sensor_t* sensor = esp_camera_sensor_get();

  if (sensor != NULL && sensor->id.PID == OV3660_PID) {
    sensor->set_vflip(sensor, 1);
    sensor->set_brightness(sensor, 0);
    sensor->set_saturation(sensor, -4);
  }

  microphone.setPinsPdmRx(MIC_CLK,MIC_DATA);
  microphone.begin(I2S_MODE_PDM_RX,16000,I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO);


  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("Wi-Fi connected.");

  server.on("/stream", HTTP_GET, handleStream);
  server.begin();


  Serial.print("Initial temperature: ");
  Serial.println(temperatureRead());
  temperatureServer.on("/temperature", HTTP_GET, handleTemperature);
  temperatureServer.begin();
  xTaskCreatePinnedToCore(temperatureServerTask, "temperatureServer", 8192, NULL, 1, NULL, 0);

  audioServer.on("/audio",HTTP_GET,handleAudio);
  audioServer.begin();

  xTaskCreatePinnedToCore(audioServerTask,"audioServer",4096,NULL,1,NULL,0);

  Serial.println();
  Serial.println("Camera stream ready.");
  Serial.print("Python stream URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/stream");
  Serial.print("Audio URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/audio");

  Serial.print("temperature URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":82/temperature");

  
}

void loop() {
  server.handleClient();
  delay(1);
}
