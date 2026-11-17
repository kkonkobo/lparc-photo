# Third-party models

LPARC Photo bundles two neural-network models. Their licence texts ship with the app, next to the models
(`src/lparc_photo/models/`).

| Model | Used for | Licence | Source |
| --- | --- | --- | --- |
| MODNet, photographic portrait matting (`modnet.onnx`) | Cutting the person out to replace the background | Apache License 2.0 | [ZHKKKe/MODNet](https://github.com/ZHKKKe/MODNet) (Ke et al., AAAI 2022); ONNX export from [Xenova/modnet](https://huggingface.co/Xenova/modnet) |
| YuNet (`yunet.onnx`) | Finding the face and its eyes and mouth for framing | MIT | [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (Wu et al.) |

Both files are unmodified. The model was chosen by measurement: on the 44 PPM-100 benchmark portraits that frame as
head-and-shoulders, BiRefNet lite was about twice as accurate as MODNet but needed 8.4 GB of memory and 7 s per
photo, against 0.3 GB and 0.1 s for MODNet. On office-style backgrounds the two give near-identical results.

`tests/data/portrait.jpg` is an AI-generated image of a fictional person, used to test framing and background
replacement.
