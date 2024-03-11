from setuptools import find_packages, setup

about = {}
with open("batch_encoding/__about__.py") as fp:
    exec(fp.read(), about)

with open("README.md", "r") as fp:
    long_description = fp.read()

setup(name='batch-video-encoding',
      version=about["__version__"],
      description=about["__summary__"],
      long_description=long_description,
      long_description_content_type="text/markdown",
      author="",
      author_email="",
      url="TBD",
      license="MIT",
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              'batchencode=batch_encoding.batchencode:main'
          ], },
      python_requires='>=3.11',
      install_requires=[
          'selfcaffeinate',
          'scruffington'
      ],
      package_data={'sw_planet_tweets': ['config/*']},
      )
