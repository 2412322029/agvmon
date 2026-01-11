#!/usr/bin/env python3

from dataparse import xml2json

def test_xml2json():
    # Test case 1: Simple XML with attributes
    xml1 = '''
    <root>
        <person id="123" name="John">
            <age>30</age>
            <city>New York</city>
        </person>
    </root>
    '''
    print("Test case 1: Simple XML with attributes")
    print("XML:")
    print(xml1)
    print("JSON:")
    print(xml2json(xml1))
    print("\n" + "="*50 + "\n")
    
    # Test case 2: XML with multiple elements of the same tag
    xml2 = '''
    <library>
        <book isbn="111">
            <title>Book 1</title>
            <author>Author 1</author>
        </book>
        <book isbn="222">
            <title>Book 2</title>
            <author>Author 2</author>
        </book>
    </library>
    '''
    print("Test case 2: XML with multiple elements of the same tag")
    print("XML:")
    print(xml2)
    print("JSON:")
    print(xml2json(xml2))
    print("\n" + "="*50 + "\n")
    
    # Test case 3: XML with Chinese content
    xml3 = '''
    <message>
        <content>你好，世界！</content>
        <sender>张三</sender>
        <timestamp>2024-01-01 12:00:00</timestamp>
    </message>
    '''
    print("Test case 3: XML with Chinese content")
    print("XML:")
    print(xml3)
    print("JSON:")
    print(xml2json(xml3))
    print("\n" + "="*50 + "\n")
    
    # Test case 4: XML with nested structure
    xml4 = '''
    <company>
        <name>Tech Corp</name>
        <departments>
            <department id="1">
                <name>Engineering</name>
                <employees>
                    <employee id="101">Alice</employee>
                    <employee id="102">Bob</employee>
                </employees>
            </department>
            <department id="2">
                <name>Marketing</name>
                <employees>
                    <employee id="201">Charlie</employee>
                </employees>
            </department>
        </departments>
    </company>
    '''
    print("Test case 4: XML with nested structure")
    print("XML:")
    print(xml4)
    print("JSON:")
    print(xml2json(xml4))
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    test_xml2json()
