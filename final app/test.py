import json
import logging
import re

logger = logging.getLogger(__name__)

def extract_json_from_text(text):
    """Extract JSON data from a text response"""
    try:
        # Find the start of the JSON object
        start_idx = text.find('{')
        if start_idx == -1:
            logger.error("No JSON object found in response")
            return None
        
        # Find the end of the JSON object
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            logger.error("Incomplete JSON object")
            return None
        
        # Extract the JSON string
        json_str = text[start_idx:end_idx+1]
        
        # Clean the JSON string
        json_str = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_str)
        
        # Parse the JSON
        return json.loads(json_str)
    except Exception as e:
        logger.error(f"Error extracting JSON: {str(e)}")
        return None

def main(file_path):
    """
    Analyze the document at the given file path and return analysis results.
    
    Args:
        file_path (str): Path to the file to analyze
        
    Returns:
        dict: Analysis results with executive_summary, sentiment_analysis, and topics
    """
    logger.info(f"Analyzing file: {file_path}")
    
    try:
        # Simulate the text response from your actual function
        # This would be replaced with your actual function call
        text_response = '''
        "8": {
          "executive_summary": "The provided text corpus is a compilation of discussions from a subreddit focused on societal collapse, spanning from 2019 to 2025. The discussions predominantly revolve around the theme of global threats and catastrophic events, with a significant emphasis on the Doomsday Clock's proximity to midnight, nuclear risks, climate change, emerging diseases, and corruption. Specific legislative concerns are highlighted in a stakeholder comment criticizing the Department of Government Efficiency's contract cancellations, calling for transparency and analysis to understand the long-term impacts. The text also includes historical data on the last week's discussions, indicating a consistent interest in these global threats over time. The corpus reveals a negative sentiment due to the focus on worsening global scenarios and the urgency for change from major powers to address these issues.",
          "sentiment_analysis": {
            "positive": {
              "percentage": 0,
              "reasoning": "No positive sentiment is present in the given text corpus."
            },
            "negative": {
              "percentage": 100,
              "reasoning": "The entire text corpus is dominated by a negative sentiment, as it consistently discusses global threats, catastrophic events, and the urgent need for action from major powers to address these issues. Specific concerns about legislation and lack of clarity in the Department of Government Efficiency's actions further contribute to this negative sentiment."
            },
            "neutral": {
              "percentage": 0,
              "reasoning": "No neutral sentiment is present in the given text corpus."
            }
          },
          "topics": {
            "Global Threats": {
              "supporting_chunks": [
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_january_1925_2025/",
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_december_30january_261024/",
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_july_1920/"
              ],
              "subtopics": [
                "Doomsday Clock",
                "Nuclear risk",
                "Climate change",
                "Emerging diseases",
                "Corruption"
              ]
            },
            "Government Actions and Transparency": {
              "supporting_chunks": [
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_january_1923/",
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_december_30january_261024/"
              ],
              "subtopics": [
                "Uncertainty and anxiety from contract cancellations",
                "Lack of clarity in criteria for cancellations",
                "Need for transparency and analysis",
                "Impact on agency planning and operations",
                "Relationship to administration's top priorities"
              ]
            },
            "Societal Collapse Interest": {
              "supporting_chunks": [
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_january_1923/",
                "https://old.reddit.com/r/collapse/comments/1ifvfri/last_week_in_collapse_december_30january_261024/"
              ],
              "subtopics": [
                "Historical interest in global threats",
                "Consistent weekly discussions"
              ]
            }
          }
        }</corpus>2025-10-06 22:15:51,513 - INFO - [2025-10-06T16:45:51.513103Z] LLM call completed in 168.19 seconds.
        '''
        
        # Extract JSON from the text response
        result = extract_json_from_text(text_response)
        
        if result is None:
            logger.error("Failed to extract JSON from response")
            return {
                "executive_summary": "Failed to analyze document due to parsing error.",
                "sentiment_analysis": {
                    "positive": {"percentage": 0, "reasoning": "Analysis failed"},
                    "negative": {"percentage": 0, "reasoning": "Analysis failed"},
                    "neutral": {"percentage": 0, "reasoning": "Analysis failed"}
                },
                "topics": {},
                "error": "Failed to extract JSON from response"
            }
        
        logger.info("Analysis completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error during analysis: {str(e)}")
        return {
            "executive_summary": "Failed to analyze document due to an unexpected error.",
            "sentiment_analysis": {
                "positive": {"percentage": 0, "reasoning": "Analysis failed"},
                "negative": {"percentage": 0, "reasoning": "Analysis failed"},
                "neutral": {"percentage": 0, "reasoning": "Analysis failed"}
            },
            "topics": {},
            "error": str(e)
        }