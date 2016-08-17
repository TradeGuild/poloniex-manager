makebase = if [ !  -d ~/.tapp ]; \
	then \
		mkdir ~/.tapp; \
	fi

makedirs = if [ !  -d ~/.tapp/poloniex ]; \
	then \
		mkdir ~/.tapp/poloniex; \
		cp cfg.ini ~/.tapp/poloniex; \
	fi

build:
	python setup.py build

install:
	$(call makebase, "")
	$(call makedirs, "")
	python setup.py -v install

clean:
	rm -rf .cache build dist *.egg-info test/__pycache__
	rm -rf test/*.pyc *.egg *~ *pyc test/*~ .eggs
	rm -f .coverage*

purge:
	rm -rf .cache build dist *.egg-info test/__pycache__
	rm -rf test/*.pyc *.egg *~ *pyc test/*~ .eggs
	rm -f .coverage*
	rm -rf ~/.tapp/poloniex
	rm -rf ~/.tapp/test
