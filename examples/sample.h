// 示例頭文件
#ifndef SAMPLE_H
#define SAMPLE_H

#include <string>

// 常量定義
const int MAX_BUFFER_SIZE = 1024;
const double PI = 3.14159265359;

// 結構體定義
struct Point {
    double x;
    double y;
    
    Point() : x(0.0), y(0.0) {}
    Point(double px, double py) : x(px), y(py) {}
};

// 函數聲明
double calculateDistance(const Point& p1, const Point& p2);
void printPoint(const Point& p);

// 命名空間
namespace Utilities {
    
    class Logger {
    private:
        std::string logFile;
        bool enabled;
        
    public:
        Logger(const std::string& file);
        void log(const std::string& message);
        void enable(bool state);
    };
    
    int factorial(int n);
    bool isPrime(int n);
}

#endif // SAMPLE_H
