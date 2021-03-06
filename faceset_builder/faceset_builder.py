
__version__ = "1.1.0"

import os
import face_recognition
import click
import re
from tqdm import tqdm
from shutil import copyfile
from faceset_builder import Frame_Collector
from faceset_builder import Photo_Collector
from string import ascii_lowercase
from itertools import product


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

def sorted_aphanumeric(data):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ] 
    return sorted(data, key=alphanum_key)

def generatePrefixes(num):
    prefixes = []
    for n in range(3, 4 + 1):
        for comb in product(ascii_lowercase, repeat=n):
            prefixes.append(''.join(comb))
            if len(prefixes) == num:
                return sorted(prefixes)

def encodeFaces(face_dir):
    face_encodings = []
    ref_faces = os.listdir(face_dir)
    for file in tqdm(ref_faces):
        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
            target_face = face_recognition.face_encodings(face_recognition.load_image_file(os.path.join(face_dir, file)))
            if len(target_face) > 0:
                face_encodings.append(target_face[0])
    return face_encodings

def processImages(file_list, face_encodings, invalid_dir, args):
    min_lumen, max_lumen = args['luminosity_range']
    pc = Photo_Collector(face_encodings, args['tolerance'], args['min_face_size'], args['crop_size'], min_lumen, max_lumen, args['laplacian_threshold'], args['one_face'], args['mask_faces'], args['save_invalid'])
    pc.setInvalidDir(invalid_dir)

    image_dir = os.path.join(args['output_dir'], "images")

    os.makedirs(image_dir, exist_ok=True)
    
    print("Removing duplicates...")
    cleaned_list = pc.cleanDuplicates(file_list, 10)
    print("Done!\n")

    print("Extracting faces...")
    pc.processPhotos(cleaned_list, image_dir, args['sample_height'])
    print("Done!\n")


def processVideos(file_list, face_encodings, invalid_dir, args):
    min_lumen, max_lumen = args['luminosity_range']
    fc = Frame_Collector(face_encodings, args['tolerance'], args['min_face_size'], args['crop_size'], min_lumen, max_lumen, args['laplacian_threshold'], args['one_face'], args['mask_faces'], args['save_invalid'])
    fc.setInvalidDir(invalid_dir)

    video_dir = os.path.join(args['output_dir'], "videos")
    os.makedirs(video_dir, exist_ok=True)
    
    for file in file_list:
        dir_name = os.path.splitext(os.path.basename(file))[0]
        file_dir = os.path.join(video_dir, dir_name)
        os.makedirs(file_dir, exist_ok=True)

        print("Extracting faces from {0}...".format(os.path.basename(file)))
        fc.processVideoFile(file, file_dir, args['scan_rate'], args['capture_rate'], args['sample_height'], args['batch_size'], args['buffer_size'], args['greedy'])
        print("Done!")
    

def collector(**kwargs):
    image_list = []
    video_list = []
    for root, _, filenames in os.walk(kwargs['source_dir']):
        for filename in filenames:
            if filename.lower().endswith(('.mp4', '.mkv', '.webm')):
                video_list.append(os.path.join(root, filename))
            elif filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                image_list.append(os.path.join(root, filename))

    os.makedirs(kwargs['output_dir'], exist_ok=True)

    invalid_dir = os.path.join(kwargs['output_dir'], "invalid")
    os.makedirs(invalid_dir, exist_ok=True)

    print("Encoding reference faces...")
    face_encodings = encodeFaces(kwargs['reference_dir'])
    print("Done!\n")
    
    print("Processing images...")
    processImages(image_list, face_encodings, invalid_dir, kwargs)

    print("Processing video files...")
    processVideos(video_list, face_encodings, invalid_dir, kwargs)
    
def compiler(**kwargs):
    compiled_list = dict()
    vid_dir = os.path.join(kwargs['source_dir'], "videos")
    img_dir = os.path.join(kwargs['source_dir'], "images")
    img_dir_list = os.listdir(img_dir)
    dir_list = os.listdir(vid_dir)

    os.makedirs(kwargs['output_dir'], exist_ok=True)
    
    prefixes = generatePrefixes(len(dir_list))
    for dir, prefix in zip(dir_list, prefixes):
        full_dir = os.path.join(vid_dir, dir)
        file_list = sorted_aphanumeric(os.listdir(full_dir))

        for f in file_list:
            if f.endswith(".jpg"):
                f_path = os.path.join(full_dir, f)
                o_path = os.path.join(kwargs['output_dir'], "{0}_{1}".format(prefix, f))
                if f_path in compiled_list:
                    print ("KEY COLLISION!!! {0}".format(f_path))
                compiled_list[f_path] = o_path
				

    file_list = sorted_aphanumeric(os.listdir(img_dir))

    for f in file_list:
        if f.endswith(".jpg"):
            f_path = os.path.join(img_dir, f)
            o_path = os.path.join(kwargs['output_dir'], "{0}_{1}".format("zzz", f))
            if f_path in compiled_list:
                print ("KEY COLLISION!!! {0}".format(f_path))
            compiled_list[f_path] = o_path
	
    for key, value in tqdm(compiled_list.items()):
       copyfile(key, value)

@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(version='1.1.0')
def faceset_builder():
    pass


@faceset_builder.command()
@click.argument('source_dir')
@click.argument('reference_dir')
@click.argument('output_dir')
@click.option('--tolerance', '-t', type=float, default=0.5, help='Threshold for face comparison. Default is 0.5.')
@click.option('--min-face-size', type=int, default=256, help='Minimum size in pixels for faces to extract. Default is 256.')

@click.option('--crop-size', type=int, default=512, help='Cropped images larger than this will be scaled down. Must be at least 1.5 times the size of --min-face-size. Default is 512.')

@click.option('--luminosity-range', type=int, nargs=2, default=(10,245), help="Range from 0-255 for acceptable face brightness. Default is 10-245.")
@click.option('--laplacian-threshold', type=float, default=0, help="Threshold for blur detection, values below this will be considered blurry. 0 means all images pass, 10 might be a good place to start. This option is very inconsistent and is not recommended, use of the --save-invalid option is strongly recommended in conjunction. Default is 0.")

@click.option('--one-face', is_flag=True, help='Discard any cropped images containing more than one face.')
@click.option('--mask-faces', is_flag=True, help='Attempt to black out unwanted faces.')

@click.option('--save-invalid', is_flag=True, help="Duplicates, corrupted files, and faces that fail validation will be saved to '<output_dir>/invalid'. Otherwise duplicates and corrupted files will be deleted, and invalid faces ignored.")

@click.option('--scan-rate', type=float, default=0.2, help='Number of frames per second to scan for reference faces. Default is 0.2 fps (1 frame every 5 seconds).')
@click.option('--capture-rate', type=float, default=5, help='Number of frames per second to extract when reference face has been found. Default is 5.')
@click.option('--sample-height', type=int, default=500, help="Height in pixel to downsample the image/frame to before running facial recognition. Default is 500. (AFFECTS VRAM)")
@click.option('--batch-size', type=int, default=32, help="Number of video frames to run facial recognition on per batch. Default is 32. (AFFECTS VRAM)")
@click.option('--buffer-size', type=int, default=-1, help='Number of frames to buffer between each scan. Default is the number of frames in one scan interval. (AFFECTS RAM)')
@click.option('--greedy', is_flag=True, help="While scanning, consider face detected even if it's smaller than --min-face-size. Might capture a few more faces at a potential performance loss.")

def collect(**kwargs):
    """Go through video files and photographs in OUTPUT_DIR and extract faces matching those found in REFERENCE_DIR. Extracted faces will be placed in OUTPUT_DIR."""
    if (kwargs['min_face_size']*1.5) > kwargs['crop_size']:
        print("ValueError: --crop-size must be larger than --min-face-size*1.5 ({0})".format(int(kwargs['min_face_size']*1.5)))
        exit()
    collector(**kwargs)
    

@faceset_builder.command()
@click.argument('source_dir')
@click.argument('output_dir')
def compile(**kwargs):
    """Compile images in SOURCE_DIR in a flat directory (OUTPUT_DIR) with sequential names"""
    compiler(**kwargs)


if __name__ == '__main__':
    setbuilder()
